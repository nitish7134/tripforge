"""Plan orchestration: brief -> stops -> transitions -> fetchers (fli, pyairbnb, places, keyless) -> plan dict.

Destination-agnostic: stops are resolved through Nominatim + OurAirports (stops.py), ground legs come
runtime routing and fare reads (ground.py). Browser fetchers are only a fallback.
"""
from __future__ import annotations

import datetime as dt
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.console import Console

from . import cache, events, ground, money
from .fetchers import airports as AP
from .fetchers import flights_fli as FL
from .fetchers import stays_pyairbnb as SP
from .fetchers.common import Result, fail
from .fetchers.geo import stay_bbox
from .fetchers.misc import fetch_advisories, fetch_climate, fetch_fx, fetch_weather
from .fetchers.visa import visa_requirement
from .fetchers.photos import fetch_photos
from .fetchers.places import stop_places
from .stops import OWN_AIRPORT_KM, StopError, airport_point, parse_spec

console = Console(stderr=True)

# Nothing currency-scaled lives here: budget_night, meal_rate, party_rate, transport_day and currency come from
# the brief (currency falls back to the home airport's country). Unit-less constants only.
DEFAULTS = {"people": 2, "budget_night": None, "prefs": [], "currency": None, "passport": None,
            "meal_rate": None, "meals_per_day": 3, "party_rate": None, "party_share": 0.5,
            "transport_day": None, "hostels": False, "flights_backend": "auto", "stays_backend": "auto",
            "browser": "headless", "alt_start": [], "end_airport": None, "country": ""}


class PlanError(ValueError):
    pass


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(str(s))


def _fmt_ts(ts: float) -> str:
    return time.strftime("%d %b %H:%M", time.localtime(ts))


# ---------------------------------------------------------------- transitions
def transitions(home: dict, stops: list[dict], start: str, end_ap: dict) -> dict:
    """Ordered hops: fly (with candidate arrival airports) or ground. Dates are per hop."""
    d = _d(start)
    hops, out_stops = [], []
    prev = {"kind": "home", "pt": home, "name": home["name"]}
    for i, s in enumerate(stops):
        cin, cout = d, d + dt.timedelta(days=s["nights"])
        out_stops.append({**s, "checkin": cin.isoformat(), "checkout": cout.isoformat()})
        hops.append(_hop(prev, i, s, d))
        prev = {"kind": "stop", "pt": s, "name": s["name"], "idx": i}
        d = cout
    hops.append(_hop(prev, None, {"home": True, **end_ap}, d, end_home=home))
    return {"start": start, "end": d.isoformat(), "nights": sum(s["nights"] for s in stops), "hops": hops,
            "stops": out_stops}


def _arr_airports(s: dict) -> list[dict]:
    main = {"iata": s["iata"], "name": s["airport"], "city": s["airport_city"], "km": s["airport_km"],
            "lat": s["airport_lat"], "lon": s["airport_lon"]}
    return [main] + list(s.get("alt_airports") or [])


def _hop(prev: dict, to_idx, s: dict, date: dt.date, end_home: dict | None = None) -> dict:
    h = {"date": date.isoformat(), "from_name": prev["name"], "to_idx": to_idx}
    if end_home is not None:  # the way home: optional ground to the end airport, then fly
        h.update(kind="fly", to_name="home", dest=[{"iata": end_home["iata"], "name": end_home["name"],
                                                    "lat": end_home["lat"], "lon": end_home["lon"], "km": 0}])
        if prev["kind"] == "stop":
            p = prev["pt"]
            h["orig"] = [{"iata": s["iata"], "name": s["name"], "city": s.get("city"), "lat": s["lat"],
                          "lon": s["lon"], "km": round(AP.km(p["lat"], p["lon"], s["lat"], s["lon"]))}]
            h["from_pt"] = p
        else:
            h["orig"] = [prev["pt"]]
        return h
    h["to_name"] = s["name"]
    if prev["kind"] == "stop" and ground.needs_ground(prev["pt"], s):
        h.update(kind="ground", a=prev["pt"], b=s)
        return h
    h["kind"] = "fly"
    if prev["kind"] == "stop":
        p = prev["pt"]
        h["orig"] = [{"iata": p["iata"], "name": p["airport"], "city": p["airport_city"], "lat": p["airport_lat"],
                      "lon": p["airport_lon"], "km": p["airport_km"]}]
        h["from_pt"] = p
    else:
        h["orig"] = [prev["pt"]]
    h["dest"] = _arr_airports(s)
    h["to_pt"] = s
    return h


def _ground_leg(a: dict, b: dict, date: str, from_name: str, to_name: str, to_idx, currency: str) -> dict:
    g = ground.estimate(a, b, currency)
    return {"kind": "ground", "date": date, "orig": a.get("iata") if a.get("is_airport") else a["name"],
            "dest": b.get("iata") if b.get("is_airport") else b["name"], "from_name": from_name, "to_name": to_name,
            "to_idx": to_idx, "rows": [], "ok": True, "ground": g}


def _gmid(g: dict) -> float:
    return ground.mid(g)


def _gadd(lo: int, hi: int, g: dict) -> tuple[int, int]:
    a = g.get("amount")
    return (lo + a[0], hi + a[1]) if a else (lo, hi)


# ---------------------------------------------------------------- fetch helpers
def fetch_flight(o: str, d: str, date: str, currency: str, backend: str, br_get, country: str) -> Result:
    params = {"o": o, "d": d, "date": date, "ccy": currency, "gl": country, "v": 1}
    if backend != "browser":
        r = cache.cached("flights:fli", params, lambda: FL.fetch_leg(o, d, date, currency, country))
        if r.ok:
            r.backend = "fli"  # type: ignore[attr-defined]
            return r
        if backend == "fli":
            return r
    br = br_get()
    if br is None:
        r2 = fail("fli empty twice and browser unavailable")
        r2.backend = "none"  # type: ignore[attr-defined]
        return r2
    from .fetchers import flights as F
    r = cache.cached("flights:browser", params, lambda: F.fetch_leg(br, o, d, date, currency, br.evid))
    r.backend = "browser"  # type: ignore[attr-defined]
    return r


class LazyBrowser:
    """Opens the Playwright browser only when a fallback actually needs it."""

    def __init__(self, mode: str, evid: Path):
        self.mode, self.evid, self.br, self.cm, self.err = mode, evid, None, None, None

    def __call__(self):
        if self.br is None and self.err is None:
            try:
                from .browser import make_browser
                self.cm = make_browser(self.mode)
                self.br = self.cm.__enter__()
                self.br.evid = self.evid
            except Exception as e:  # noqa: BLE001
                self.err = str(e)
        return self.br

    def close(self):
        if self.cm:
            try:
                self.cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass


def fetch_stay(s: dict, cin: str, cout: str, people: int, budget: int, currency: str, backend: str, br_get,
               room_type: str = "Entire home/apt") -> Result:
    params = {"name": s["name"], "cc": s["cc"], "cin": cin, "cout": cout, "p": people, "b": budget,
              "ccy": currency, "rt": room_type, "v": 1}
    if backend != "browser":
        def go():
            bb = stay_bbox(s["name"], s.get("country", ""), (s.get("areas") or [[None]])[0][0], s["lat"], s["lon"],
                           s.get("stay_center"))
            return SP.fetch_stay(bb, s.get("airbnb", ""), cin, cout, s["nights"], people, budget, currency, room_type)
        r = cache.cached("stays:pyairbnb", params, go)
        if r.ok or backend == "pyairbnb":
            r.backend = "pyairbnb"  # type: ignore[attr-defined]
            return r
    br = br_get()
    if br is None:
        r2 = fail("pyairbnb found nothing and browser unavailable")
        r2.backend = "none"  # type: ignore[attr-defined]
        return r2
    from .fetchers import stays as S
    r = cache.cached("stays:browser", params, lambda: S.fetch_stay(
        br, s.get("airbnb", ""), cin, cout, s["nights"], people, budget, currency, br.evid,
        s["name"].replace(" ", ""), room_type))
    r.backend = "browser"  # type: ignore[attr-defined]
    return r


# ---------------------------------------------------------------- day plan
def day_items(s: dict, places: dict, prefs: list[str]) -> list[str]:
    hl = list(s.get("highlights") or [])
    sights = [p["name"] + (f" ({p['price']})" if p.get("price") else "") for p in places.get("sights", [])]
    items = []
    for i in range(max(len(sights), len(hl))):
        if i < len(sights):
            items.append(sights[i])
        if i < len(hl) and hl[i] not in items:
            items.append(hl[i])
    return items or [f"Explore {s['name']}"]


def build_days(opt: dict, places: dict, prefs: list[str]) -> list[dict]:
    out = []
    legs = opt["legs"]
    for i, s in enumerate(opt["stops"]):
        arr = [lg for lg in legs if lg.get("to_idx") == i]
        fl = next((lg for lg in arr if lg["kind"] == "flight" and lg["rows"]), None)
        p = places.get(s["name"], {})
        items = day_items(s, p, prefs)
        veg = [x["name"] for x in p.get("veg", [])]
        night = [x["name"] for x in p.get("nightlife", [])]
        d0 = _d(s["checkin"])
        for k in range(s["nights"]):
            text = items[k % len(items)]
            if k == 0 and fl:
                text = f"Arrive {fl['rows'][0]['arr']} on {fl['rows'][0]['flight']}" + (
                    " then " + arr[-1]["ground"]["mode"] if arr[-1]["kind"] == "ground" else "") + ". " + text
            elif k == 0 and arr and arr[-1]["kind"] == "ground":
                text = f"Transfer by {arr[-1]['ground']['mode']} (about {arr[-1]['ground']['hours'][0]}h). " + text
            extra = []
            if "veg" in prefs and veg:
                extra.append(f"veg: {veg[k % len(veg)]}")
            if "party" in prefs and night and k % 2 == 0:
                extra.append(f"night out: {night[(k // 2) % len(night)]}")
            out.append({"date": (d0 + dt.timedelta(days=k)).strftime("%a %d %b"), "place": s["name"], "text": text,
                        "extra": "; ".join(extra)})
    last = next((lg for lg in reversed(legs) if lg["kind"] == "flight"), None)
    p = last["rows"][0] if last and last["rows"] else None
    out.append({"date": _d(opt["end"]).strftime("%a %d %b"), "place": "Return", "extra": "",
                "text": (f"Fly home {p['flight']} {p['dep']} from {last['orig']}." if p
                         else f"Fly home from {last['orig'] if last else 'the last airport'}.")})
    return out


SPEND_PLACEHOLDER = "set meal_rate/party_rate in brief.yaml to see daily spend"


def daily_spend(cfg: dict, days: int, party_n: int, wants_party: bool) -> tuple[list, int | None, str | None]:
    """Daily spend rows from the brief's own rates. No invented numbers: without meal_rate (or party_rate when
    the trip is a party trip) the section is a placeholder and no total is produced."""
    meal, party_r, trans = cfg.get("meal_rate"), cfg.get("party_rate"), cfg.get("transport_day")
    if meal is None or (wants_party and party_r is None):
        return [], None, SPEND_PLACEHOLDER
    rows = [{"label": f"Meals ({cfg['meals_per_day']} a day x {days} days at {meal:,})",
             "amount": days * cfg["meals_per_day"] * meal}]
    if wants_party:
        rows.append({"label": f"Party nights ({party_n} at {party_r:,})", "amount": party_n * party_r})
    if trans is not None:
        rows.append({"label": f"Local transport ({days} days at {trans:,})", "amount": days * trans})
    return rows, sum(r["amount"] for r in rows), None


def visa_targets(home_cc: str, passport: str, stop_ccs) -> list[str]:
    """Countries needing a visa lookup: not the home airport's country, not the passport's own. A domestic trip
    (every stop in the home country) returns [] so the plan shows no visa section at all."""
    return sorted({c for c in stop_ccs if c and c != home_cc and c != passport})


# ---------------------------------------------------------------- main
def run_plan(cfg: dict, evid: Path) -> dict:
    t0 = time.time()
    cfg = {**DEFAULTS, **{k: v for k, v in cfg.items() if v is not None}}
    if not cfg.get("stops") or not cfg.get("start"):
        raise PlanError("brief needs at least stops and start (plus from: <IATA> or home_city)")
    prefs = [p.strip().lower() for p in (cfg["prefs"] if isinstance(cfg["prefs"], list) else str(cfg["prefs"]).split(","))
             if p.strip()]
    try:
        home_ap = AP.resolve_home(cfg)
        currency = money.resolve_currency(cfg, home_ap["cc"])
    except ValueError as e:
        raise PlanError(str(e)) from e
    cfg["from"] = home_ap["iata"]
    people = int(cfg["people"])
    budget = int(cfg["budget_night"]) if cfg.get("budget_night") else 0  # 0 = no nightly cap on stay searches
    cfg["passport"] = str(cfg.get("passport") or home_ap["cc"]).upper()  # default: the home country's passport
    home = {"iata": home_ap["iata"], "name": home_ap["city"] or home_ap["name"], "lat": home_ap["lat"],
            "lon": home_ap["lon"], "km": 0}
    end_ap = AP.by_iata(cfg["end_airport"]) if cfg.get("end_airport") else None
    if cfg.get("end_airport") and not end_ap:
        raise PlanError(f"unknown end airport {cfg['end_airport']}")
    try:
        stops = parse_spec(cfg["stops"], cfg.get("country", ""))
    except StopError as e:
        raise PlanError(str(e)) from e
    last = stops[-1]
    if end_ap is None:
        end_ap = AP.by_iata(last["iata"])
    end_pt = {"iata": end_ap["iata"], "name": end_ap["city"] or end_ap["name"], "lat": end_ap["lat"],
              "lon": end_ap["lon"]}
    starts = [str(cfg["start"]), *[str(x) for x in (cfg.get("alt_start") or [])]]
    options = [transitions(home, stops, s, end_pt) for s in starts]
    evid.mkdir(parents=True, exist_ok=True)
    photo_dir = cache.repo_root() / "cache" / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    ccs = sorted({s["cc"] for s in stops})
    cnames = {s["cc"]: s["country"] for s in stops}
    br = LazyBrowser(cfg["browser"], evid)

    need_f = sorted({(o_["iata"], d_["iata"], h["date"]) for o in options for h in o["hops"] if h["kind"] == "fly"
                     for o_ in h["orig"] for d_ in h["dest"] if o_["iata"] != d_["iata"]}, key=lambda x: x[2])
    need_s = sorted({(i, s["checkin"], s["checkout"]) for o in options for i, s in enumerate(o["stops"])},
                    key=lambda x: x[1])
    console.print(f"[bold]fetching[/bold] {len(need_f)} flight queries (backend {cfg['flights_backend']}), "
                  f"{len(need_s)} stay searches, places for {len(stops)} stops")

    with ThreadPoolExecutor(max_workers=12) as ex:
        pl_f = {s["name"]: ex.submit(stop_places, s) for s in stops}
        cur_f = {cc: ex.submit(money.country_currency, cc) for cc in ccs}
        adv_f = ex.submit(fetch_advisories, cnames, evid)
        clim_f = {s["name"]: ex.submit(lambda s=s: cache.cached("climate", {"i": s["iata"], "m": _d(starts[0]).month},
                                                                lambda: fetch_climate(s["iata"], _d(starts[0]).month, evid)))
                  for s in stops}
        wx_f = {s["name"]: ex.submit(fetch_weather, s["lat"], s["lon"], starts[0], options[0]["end"], evid, s["name"])
                for s in stops}
        ph_f = {s["name"]: ex.submit(fetch_photos, f"{s['name']} {s['country']}", 2, photo_dir) for s in stops}
        # fli is a thin HTTP client; 4 in flight is polite and fast. Browser fallback is serialised by LazyBrowser.
        with ThreadPoolExecutor(max_workers=4) as fx_ex:
            # Browser fallback only for each hop's primary airport pair; alternates are fli-only.
            prim = {(h["orig"][0]["iata"], h["dest"][0]["iata"], h["date"]) for o in options for h in o["hops"]
                    if h["kind"] == "fly"}
            fl_f = {k: fx_ex.submit(fetch_flight, *k, currency,
                                    cfg["flights_backend"] if k in prim or cfg["flights_backend"] == "browser" else "fli",
                                    br, home_ap["cc"]) for k in need_f}
            stop_for = {(i, s["checkin"], s["checkout"]): s for o in options for i, s in enumerate(o["stops"])}
            st_f = {k: fx_ex.submit(fetch_stay, stop_for[k], k[1], k[2], people, budget, currency,
                                    cfg["stays_backend"], br) for k in need_s}
            rm_f = {}
            if cfg["hostels"]:
                rm_f = {k: fx_ex.submit(fetch_stay, stop_for[k], k[1], k[2], people, (max(int(budget * 0.4), 1) if budget else 0),
                                        currency, "pyairbnb", br, "Private room") for k in need_s}
            flights = {k: f.result() for k, f in fl_f.items()}
            stays = {k: f.result() for k, f in st_f.items()}
            rooms = {k: f.result() for k, f in rm_f.items()}
        console.print(f"  flights+stays done in {time.time() - t0:.0f}s")
        places = {k: f.result() for k, f in pl_f.items()}
        curr = {k: f.result() for k, f in cur_f.items()}
        adv = adv_f.result()
        clim = {k: f.result() for k, f in clim_f.items()}
        wx = {k: f.result() for k, f in wx_f.items()}
        photos = {k: f.result() for k, f in ph_f.items()}
    br.close()
    local_ccys = sorted({r.data for r in curr.values() if r.ok and r.data and r.data != currency})
    fx = {c: cache.cached("fx", {"s": c, "d": currency}, lambda c=c: fetch_fx(c, currency, evid)) for c in local_ccys}
    # Domestic trips (every stop in the home airport's country) and stops in the passport country need no visa.
    visa = {cc: visa_requirement(cfg["passport"], cc) for cc in visa_targets(home_ap["cc"], cfg["passport"], ccs)}

    # ---- assemble options
    out_opts = []
    for o in options:
        legs, fl_total, fl_missing, g_lo, g_hi = [], 0, 0, 0, 0
        for h in o["hops"]:
            if h["kind"] == "ground":
                lg = _ground_leg(h["a"], h["b"], h["date"], h["from_name"], h["to_name"], h["to_idx"], currency)
                legs.append(lg)
                g_lo, g_hi = _gadd(g_lo, g_hi, lg["ground"])
                continue
            # choose the cheapest (flight + onward ground) among candidate arrival airports
            best = None
            for org in h["orig"]:
                for dst in h["dest"]:
                    r = flights.get((org["iata"], dst["iata"], h["date"]))
                    allrows = (r.data or []) if r and r.ok else []
                    rows = ([x for x in allrows if x.get("price") is not None] + [x for x in allrows if x.get("price") is None])[:3]
                    post = None
                    if h.get("to_pt") and (dst.get("km", 0) > OWN_AIRPORT_KM or dst["iata"] != h["to_pt"]["iata"]):
                        post = ground.estimate(airport_point(dst), h["to_pt"], currency)
                    pre = None
                    if h.get("from_pt") and org.get("km", 0) > OWN_AIRPORT_KM:
                        pre = ground.estimate(h["from_pt"], airport_point(org), currency)
                    cost = (rows[0]["price"] if rows and rows[0]["price"] is not None else math.inf) + (_gmid(post) if post else 0) + (_gmid(pre) if pre else 0)
                    cand = {"org": org, "dst": dst, "r": r, "rows": rows, "pre": pre, "post": post, "cost": cost}
                    if best is None or cost < best["cost"]:
                        best = cand
            r = best["r"]
            if best["pre"]:
                lg = _ground_leg(h["from_pt"], airport_point(best["org"]), h["date"], h["from_name"],
                                 f"{best['org']['iata']} airport", None, currency)
                legs.append(lg)
                g_lo, g_hi = _gadd(g_lo, g_hi, lg["ground"])
            alts = [{"iata": d_["iata"], "price": (lambda rr: rr.data[0]["price"] if rr and rr.ok and rr.data else None)(
                flights.get((best["org"]["iata"], d_["iata"], h["date"])))} for d_ in h["dest"] if d_ is not best["dst"]]
            legs.append({"kind": "flight", "date": h["date"], "orig": best["org"]["iata"], "dest": best["dst"]["iata"],
                         "from_name": h["from_name"], "to_name": h["to_name"] if not best["post"] else
                         f"{best['dst'].get('city') or best['dst']['iata']} (for {h['to_name']})",
                         "to_idx": h["to_idx"], "rows": best["rows"], "ok": bool(best["rows"]),
                         "source_url": r.source_url if r else "", "screenshot": r.screenshot_path if r else None,
                         "backend": getattr(r, "backend", "none") if r else "none",
                         "fetched": _fmt_ts(r.fetched_at) if r and r.ok else None,
                         "cached": bool(getattr(r, "cached", False)) if r else False, "alts": alts,
                         "error": None if best["rows"] else (r.error if r else "not fetched")})
            if best["rows"] and best["rows"][0]["price"] is not None:
                fl_total += best["rows"][0]["price"]
            else:
                fl_missing += 1
            if best["post"]:
                lg = _ground_leg(airport_point(best["dst"]), h["to_pt"], h["date"], f"{best['dst']['iata']} airport",
                                 h["to_name"], h["to_idx"], currency)
                legs.append(lg)
                g_lo, g_hi = _gadd(g_lo, g_hi, lg["ground"])

        st_total, st_missing, stop_out = 0, 0, []
        for i, s in enumerate(o["stops"]):
            r = stays.get((i, s["checkin"], s["checkout"]))
            cands = r.data["ranked"][:3] if r and r.ok else []
            if cands:
                st_total += cands[0]["total"]
            else:
                st_missing += 1
            rr = rooms.get((i, s["checkin"], s["checkout"]))
            pl = places.get(s["name"], {})
            stop_out.append({**{k: s.get(k) for k in ("name", "iata", "cc", "country", "nights", "checkin", "checkout",
                                                      "airport", "airport_km")},
                             "areas": s.get("areas") or [], "highlights": s.get("highlights") or [],
                             "guide_found": s.get("guide_found"), "guide_url": s.get("guide_url"),
                             "places": {k: pl.get(k, []) for k in ("veg", "nightlife", "sights")},
                             "places_sources": pl.get("sources", []),
                             "stays": cands, "stay_ok": bool(cands),
                             "stay_error": None if cands else (r.error if r else "not fetched"),
                             "stay_backend": getattr(r, "backend", "none") if r else "none",
                             "stay_fetched": _fmt_ts(r.fetched_at) if r and r.ok else None,
                             "stay_url": r.source_url if r else "", "stay_shot": r.screenshot_path if r else None,
                             "rooms": (rr.data["ranked"][:2] if rr and rr.ok else [])})
        days = o["nights"] + 1
        party_n = sum(math.ceil(s["nights"] * cfg["party_share"]) for s in o["stops"]) if "party" in prefs else 0
        spend_rows, spend_pp, spend_note = daily_spend(cfg, days, party_n, "party" in prefs)
        o2 = {**o, "legs": legs, "stops": stop_out}
        o2.pop("hops", None)
        o2["totals"] = {"flights_pp": fl_total, "flight_legs_missing": fl_missing, "stays_total": st_total,
                        "stays_pp": round(st_total / people), "stays_missing": st_missing,
                        "ground_lo_pp": g_lo, "ground_hi_pp": g_hi, "days": days, "party_nights": party_n,
                        "spend_rows": spend_rows, "spend_pp": spend_pp, "spend_note": spend_note,
                        "core_pp": fl_total + round(st_total / people),
                        "all_in_lo_pp": fl_total + round(st_total / people) + g_lo + (spend_pp or 0),
                        "all_in_hi_pp": fl_total + round(st_total / people) + g_hi + (spend_pp or 0)}
        o2["days_plan"] = build_days(o2, {s["name"]: s["places"] for s in stop_out}, prefs)
        out_opts.append(o2)

    ev = []
    for label, r in ([(f"flights {k[0]}-{k[1]} {k[2]} [{getattr(v, 'backend', '')}]", v) for k, v in flights.items()] +
                     [(f"stays {stops[k[0]]['name']} {k[1]} [{getattr(v, 'backend', '')}]", v) for k, v in stays.items()] +
                     [(f"fx {k}", v) for k, v in fx.items()] + [(f"advisory {k}", v) for k, v in adv.items()] +
                     [(f"climate {k}", v) for k, v in clim.items()] + [(f"visa {k}", v) for k, v in visa.items()]):
        ev.append({"label": label, "ok": r.ok, "url": r.source_url,
                   "file": Path(r.screenshot_path).name if r.screenshot_path else None,
                   "fetched_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(r.fetched_at)), "error": r.error,
                   "cached": bool(getattr(r, "cached", False))})
    for name, p in places.items():
        for src in p.get("sources", []):
            ev.append({"label": f"places {name}: {src['label']}", "ok": src["ok"], "url": src["url"], "file": None,
                       "fetched_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(src["fetched_at"])),
                       "error": src["error"], "cached": False})
    win_s, win_e = _d(starts[0]), _d(options[0]["end"])
    ev_rows = events.lunar_rows(win_s, win_e, [(places[s["name"]].get("lead") or "") for s in stops])
    backends = {"flights": sorted({getattr(v, "backend", "none") for v in flights.values()}),
                "stays": sorted({getattr(v, "backend", "none") for v in stays.values()})}
    return {
        "meta": {"home": home["iata"], "home_name": home["name"], "people": people, "budget_night": budget or None,
                 "prefs": prefs, "currency": currency, "budget_set": bool(budget), "passport": cfg["passport"],
                 "generated": time.strftime("%d %b %Y %H:%M"), "browser": cfg["browser"],
                 "title": " + ".join(s["name"] for s in stops), "end_airport": end_pt["iata"],
                 "rates": {k: cfg.get(k) for k in ("meal_rate", "meals_per_day", "party_rate", "party_share", "transport_day")},
                 "backends": backends, "cache": cache.stats(), "wall_s": round(time.time() - t0, 1)},
        "options": out_opts,
        "events": ev_rows,
        "fx": {k: v.data for k, v in fx.items() if v.ok},
        "advisory": {cc: (r.data | {"url": r.source_url}) if r.ok else {"error": r.error} for cc, r in adv.items()},
        "climate": {k: (r.data | {"url": r.source_url}) if r.ok else {"error": r.error} for k, r in clim.items()},
        "weather": {k: (r.data if r.ok else {"error": r.error}) for k, r in wx.items()},
        "visa": {cc: (r.data | {"source": r.source_url, "fetched": _fmt_ts(r.fetched_at)}) if r.ok
                 else {"error": r.error, "source": r.source_url} for cc, r in visa.items()},
        "countries": cnames,
        "photos": {k: (r.data if r.ok else []) for k, r in photos.items()},
        "evidence": ev,
    }
