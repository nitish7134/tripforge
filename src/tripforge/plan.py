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
from .fetchers import rail as RL
from .fetchers import stays_pyairbnb as SP
from .fetchers.common import Result, fail
from .fetchers.geo import stay_bbox
from .fetchers.advisory import fetch_advisories
from .fetchers.climate import fetch_normals
from .fetchers.misc import fetch_fx, fetch_weather
from .fetchers.visa import visa_requirement
from .fetchers.photos import fetch_photos
from .fetchers.places import diets_in, stop_places, wikivoyage
from .stops import OWN_AIRPORT_KM, StopError, airport_point, parse_spec

console = Console(stderr=True)

# Nothing currency-scaled lives here: budget_night, meal_rate, party_rate, transport_day and currency come from
# the brief (currency falls back to the home airport's country). Unit-less constants only.
DEFAULTS = {"people": 2, "budget_night": None, "prefs": [], "currency": None, "passport": None,
            "meal_rate": None, "meals_per_day": 3, "party_rate": None, "party_share": 0.5,
            "transport_day": None, "hostels": False, "max_ground_hours": 6, "flights_backend": "auto", "stays_backend": "auto",
            "browser": "headless", "alt_start": [], "end_airport": None, "country": "",
            "ground": {}, "flights": {}, "stays": {}, "pace": "balanced"}


class PlanError(ValueError):
    pass


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(str(s))


def _fmt_ts(ts: float) -> str:
    return time.strftime("%d %b %H:%M", time.localtime(ts))


# ---------------------------------------------------------------- transitions
def transitions(home: dict, stops: list[dict], start: str, end_ap: dict, max_km: float = ground.GROUND_MAX_KM) -> dict:
    """Ordered hops: fly (with candidate arrival airports) or ground. Dates are per hop."""
    d = _d(start)
    hops, out_stops = [], []
    prev = {"kind": "home", "pt": home, "name": home["name"]}
    for i, s in enumerate(stops):
        cin, cout = d, d + dt.timedelta(days=s["nights"])
        out_stops.append({**s, "checkin": cin.isoformat(), "checkout": cout.isoformat()})
        hops.append(_hop(prev, i, s, d, max_km=max_km))
        prev = {"kind": "stop", "pt": s, "name": s["name"], "idx": i}
        d = cout
    hops.append(_hop(prev, None, {"home": True, **end_ap}, d, end_home=home, max_km=max_km))
    return {"start": start, "end": d.isoformat(), "nights": sum(s["nights"] for s in stops), "hops": hops,
            "stops": out_stops}


def _arr_airports(s: dict) -> list[dict]:
    main = {"iata": s["iata"], "name": s["airport"], "city": s["airport_city"], "km": s["airport_km"],
            "lat": s["airport_lat"], "lon": s["airport_lon"]}
    return [main] + list(s.get("alt_airports") or [])


def _hop(prev: dict, to_idx, s: dict, date: dt.date, end_home: dict | None = None,
         max_km: float = ground.GROUND_MAX_KM) -> dict:
    h = {"date": date.isoformat(), "from_name": prev["name"], "to_idx": to_idx}
    if end_home is not None and prev["kind"] == "stop" and ground.needs_ground(prev["pt"], end_home, max_km):
        h.update(kind="ground", a=prev["pt"], b=end_home, to_name="home")  # close enough to go home by road
        return h
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
    if ground.needs_ground(prev["pt"], s, max_km):
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
              "ccy": currency, "rt": room_type, "v": 2}
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


# ---------------------------------------------------------------- rail + pace helpers
RAIL_MAX_HOURS = 18  # brief key ground.rail_max_hours overrides
PACE_SIGHTS = {"relaxed": 2, "balanced": 3, "packed": 4}  # sights per day
EARLY_MIN = 8 * 60  # relaxed pace avoids transfers that start before 08:00


def wants_nightlife(prefs: list[str], cfg: dict) -> bool:
    """Party / bars sections exist only for travellers who asked for them (pref or a party budget)."""
    return any(p in ("party", "nightlife") for p in prefs) or (cfg.get("party_rate") or 0) > 0


def hop_ends(o: dict, home: dict, home_cc: str) -> list[tuple]:
    """[(hop, from_name, to_name, from_cc, to_cc)] for the hops of one option, in order."""
    out, pname, pcc = [], home["name"], home_cc
    for h in o["hops"]:
        if h["to_idx"] is None:
            tname, tcc = home["name"], home_cc
        else:
            st = o["stops"][h["to_idx"]]
            tname, tcc = st["name"], st["cc"]
        out.append((h, pname, tname, pcc, tcc))
        pname, pcc = tname, tcc
    return out


def rail_leg(h: dict, fname: str, tname: str, q: dict, note: dict | None, pace: str) -> dict:
    rows = list(q.get("rows") or [])
    if pace == "relaxed":  # prefer a civilised departure, then the shortest
        rows.sort(key=lambda r: (r["dep_min"] < EARLY_MIN, r["duration_min"]))
    for r in rows:
        r["next_day"] = r["dep_min"] + r["duration_min"] >= 1440
        r["early"] = r["dep_min"] < EARLY_MIN
    return {"kind": "rail", "date": h["date"], "from_name": fname, "to_name": tname, "to_idx": h["to_idx"],
            "rows": rows, "ok": bool(rows), "error": q.get("error"), "source_url": q.get("url", ""),
            "adapter": q.get("adapter"), "dropped": q.get("dropped", 0), "note": note, "used": False,
            "fetched": _fmt_ts(q["fetched_at"]) if q.get("fetched_at") else None, "tag": "indicative"}


def _rail_for(h: dict, ends: dict, rails: dict, by_train: dict, pace: str) -> dict | None:
    _, fn, tn, fcc, tcc = ends[id(h)]
    q = rails.get((fn, tn, fcc, h["date"]))
    if q is None or fcc != tcc or fn == tn:
        return None
    r = by_train.get(tn)
    return rail_leg(h, fn, tn, q, r if r else None, pace)


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


def _arrival(arr: list[dict]) -> tuple[str, dict | None]:
    """The way this stop is reached, as day-plan text: the leg the totals use (flight, else used rail)."""
    fl = next((lg for lg in arr if lg["kind"] == "flight" and lg["rows"]), None)
    rl = next((lg for lg in arr if lg["kind"] == "rail" and lg.get("used")), None)
    if fl and not (rl and not fl["rows"][0].get("price")):
        r = fl["rows"][0]
        return f"Arrive {r['arr']} on {r['flight']}" + (" (one stop)" if fl.get("one_stop") else ""), fl
    if rl and rl["rows"]:
        r = rl["rows"][0]
        return (f"Arrive {r['arr']}{' next day' if r.get('next_day') else ''} by train {r['train']} {r['name']}"
                + (f" (departs {r['dep']}, an early start)" if r.get("early") else "")), rl
    return "", None


def build_days(opt: dict, places: dict, prefs: list[str], pace: str = "balanced", night_on: bool | None = None) -> list[dict]:
    """One row per night. Pace caps the sights a day carries; nightlife appears only when the traveller wants it."""
    out = []
    legs = opt["legs"]
    per_day = PACE_SIGHTS.get(pace, 3)
    if night_on is None:
        night_on = "party" in prefs
    for i, s in enumerate(opt["stops"]):
        arr = [lg for lg in legs if lg.get("to_idx") == i]
        p = places.get(s["name"], {})
        items = day_items(s, p, prefs)
        diet = {d: [x["name"] for x in v] for d, v in (p.get("diet") or {}).items()}
        night = [x["name"] for x in p.get("nightlife", [])] if night_on else []
        d0 = _d(s["checkin"])
        cur = 0
        for k in range(s["nights"]):
            n = max(1, per_day - 1) if k == 0 and arr else per_day  # a travel day carries one sight fewer
            picked = [items[(cur + j) % len(items)] for j in range(min(n, len(items)))]
            cur += len(picked)
            text = "; ".join(dict.fromkeys(picked))
            road = next((lg for lg in arr if lg["kind"] == "ground" and not lg.get("alt")), None)
            if k == 0:
                head, _ = _arrival(arr)
                if head:
                    text = head + (f", then {road['ground']['mode']}" if road and arr[-1] is road else "") + ". " + text
                elif road:
                    text = f"Transfer by {road['ground']['mode']} (about {road['ground']['hours'][0]}h). " + text
            extra = []
            for d, names in diet.items():
                if names:
                    extra.append(f"{d}: {names[k % len(names)]}")
            if night_on and "party" in prefs and night and k % 2 == 0:
                extra.append(f"night out: {night[(k // 2) % len(night)]}")
            out.append({"date": (d0 + dt.timedelta(days=k)).strftime("%a %d %b"), "place": s["name"], "text": text,
                        "extra": "; ".join(extra)})
    last = legs[-1] if legs else None
    end = _d(opt["end"]).strftime("%a %d %b")
    ret = [lg for lg in legs if lg.get("to_idx") is None]
    rl = next((lg for lg in ret if lg["kind"] == "rail" and lg.get("used") and lg["rows"]), None)
    fl = next((lg for lg in reversed(ret) if lg["kind"] == "flight"), None)
    if rl and not (fl and fl["rows"] and fl["rows"][0].get("price")):
        r = rl["rows"][0]
        return out + [{"date": end, "place": "Return", "extra": "",
                       "text": f"Train home {r['train']} {r['name']}, departs {r['dep']}, arrives {r['arr']}"
                               f"{' next day' if r.get('next_day') else ''}."}]
    if last and last["kind"] == "ground" and not last.get("alt") and not fl:
        return out + [{"date": end, "place": "Return", "extra": "",
                       "text": f"Head home by {last['ground']['mode']} (about {last['ground']['hours'][0]}h)."}]
    p = fl["rows"][0] if fl and fl["rows"] else None
    out.append({"date": end, "place": "Return", "extra": "",
                "text": (f"Fly home {p['flight']} {p['dep']} from {fl['orig']}." if p
                         else f"Fly home from {fl['orig'] if fl else 'the last airport'}.")})
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
    gset, fset, sset = (cfg.get(k) or {} for k in ("ground", "flights", "stays"))
    rail_ok = bool(gset.get("rail_ok"))
    night_ok = bool(gset.get("night_travel_ok", True))
    rail_max = float(gset.get("rail_max_hours", RAIL_MAX_HOURS))
    stop_h = float(fset["max_total_hours_if_stop"]) if fset.get("max_total_hours_if_stop") else None
    guests = int(sset.get("guests", people))  # who the stay must sleep; cost is still split over `people`
    pace = str(cfg.get("pace") or "balanced").lower()
    night_on = wants_nightlife(prefs, cfg)
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
    options = [transitions(home, stops, s, end_pt, float(cfg["max_ground_hours"]) * 60) for s in starts]
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
        pl_f = {s["name"]: ex.submit(stop_places, s, diets_in(prefs)) for s in stops}
        cur_f = {cc: ex.submit(money.country_currency, cc) for cc in ccs}
        foreign = {cc: n for cc, n in cnames.items() if cc != home_ap["cc"]}  # domestic: nothing to advise on
        adv_f = ex.submit(fetch_advisories, cfg["passport"], foreign, evid) if foreign else None
        clim_f = {s["name"]: ex.submit(fetch_normals, s["lat"], s["lon"], _d(starts[0]).month) for s in stops}
        hol_win = (_d(starts[0]), _d(options[0]["end"]))
        hol_f = {cc: ex.submit(events.public_holidays, cc, *hol_win) for cc in sorted({home_ap["cc"], *ccs})}
        wx_f = {s["name"]: ex.submit(fetch_weather, s["lat"], s["lon"], starts[0], options[0]["end"], evid, s["name"])
                for s in stops}
        ph_f = {s["name"]: ex.submit(fetch_photos, f"{s['name']} {s['country']}", 2, photo_dir) for s in stops}
        rail_f, bt_f = {}, {}
        if rail_ok:  # rail quotes per hop + the destination's own "By train" text, read in parallel
            for o in options:
                for h, fn, tn, fcc, tcc in hop_ends(o, home, home_ap["cc"]):
                    if fcc == tcc and fn != tn:
                        rail_f[(fn, tn, fcc, h["date"])] = ex.submit(RL.quote, fn, tn, fcc, h["date"], rail_max, night_ok)
                        bt_f.setdefault(tn, ex.submit(RL.by_train_note, tn))
        # fli is a thin HTTP client; 4 in flight is polite and fast. Browser fallback is serialised by LazyBrowser.
        with ThreadPoolExecutor(max_workers=4) as fx_ex:
            # Browser fallback only for each hop's primary airport pair; alternates are fli-only.
            prim = {(h["orig"][0]["iata"], h["dest"][0]["iata"], h["date"]) for o in options for h in o["hops"]
                    if h["kind"] == "fly"}
            fl_f = {k: fx_ex.submit(fetch_flight, *k, currency,
                                    cfg["flights_backend"] if k in prim or cfg["flights_backend"] == "browser" else "fli",
                                    br, home_ap["cc"]) for k in need_f}
            stop_for = {(i, s["checkin"], s["checkout"]): s for o in options for i, s in enumerate(o["stops"])}
            st_f = {k: fx_ex.submit(fetch_stay, stop_for[k], k[1], k[2], guests, budget, currency,
                                    cfg["stays_backend"], br) for k in need_s}
            rm_f = {}
            if cfg["hostels"]:
                rm_f = {k: fx_ex.submit(fetch_stay, stop_for[k], k[1], k[2], guests, (max(int(budget * 0.4), 1) if budget else 0),
                                        currency, "pyairbnb", br, "Private room") for k in need_s}
            flights = {k: f.result() for k, f in fl_f.items()}
            stays = {k: f.result() for k, f in st_f.items()}
            rooms = {k: f.result() for k, f in rm_f.items()}
        console.print(f"  flights+stays done in {time.time() - t0:.0f}s")
        places = {k: f.result() for k, f in pl_f.items()}
        curr = {k: f.result() for k, f in cur_f.items()}
        adv = adv_f.result() if adv_f else {}
        hol = {cc: f.result() for cc, f in hol_f.items()}
        clim = {k: f.result() for k, f in clim_f.items()}
        wx = {k: f.result() for k, f in wx_f.items()}
        photos = {k: f.result() for k, f in ph_f.items()}
        rails = {k: f.result() for k, f in rail_f.items()}
        by_train = {k: f.result() for k, f in bt_f.items()}
    br.close()
    local_ccys = sorted({r.data for r in curr.values() if r.ok and r.data and r.data != currency})
    fx = {c: cache.cached("fx", {"s": c, "d": currency}, lambda c=c: fetch_fx(c, currency, evid)) for c in local_ccys}
    # Domestic trips (every stop in the home airport's country) and stops in the passport country need no visa.
    visa = {cc: visa_requirement(cfg["passport"], cc) for cc in visa_targets(home_ap["cc"], cfg["passport"], ccs)}

    # ---- assemble options
    out_opts = []
    for o in options:
        legs, fl_total, fl_missing, g_lo, g_hi, rail_missing = [], 0, 0, 0, 0, 0
        ends = {id(e[0]): e for e in hop_ends(o, home, home_ap["cc"])}
        for h in o["hops"]:
            if h["kind"] == "ground":
                lg = _ground_leg(h["a"], h["b"], h["date"], h["from_name"], h["to_name"], h["to_idx"], currency)
                legs.append(lg)
                g_lo, g_hi = _gadd(g_lo, g_hi, lg["ground"])
                rl = _rail_for(h, ends, rails, by_train, pace)
                if rl:
                    legs.append(rl)  # road is the priced row; rail is shown beside it
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
            one_stop = False
            if not best["rows"] and stop_h:  # no nonstop: one stop within the brief's total-time limit
                r1 = cache.cached("flights:fli1", {"o": best["org"]["iata"], "d": best["dst"]["iata"], "date": h["date"],
                                                   "ccy": currency, "gl": home_ap["cc"], "h": stop_h, "v": 1},
                                  lambda: FL.fetch_leg_one_stop(best["org"]["iata"], best["dst"]["iata"], h["date"],
                                                                currency, home_ap["cc"], stop_h))
                if r1.ok and r1.data:
                    best["rows"] = ([x for x in r1.data if x.get("price") is not None] + [x for x in r1.data if x.get("price") is None])[:3]
                    r, one_stop = r1, True
                    r.backend = "fli"  # type: ignore[attr-defined]
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
                         "one_stop": one_stop,
                         "error": None if best["rows"] else (r.error if r else "not fetched")})
            priced = bool(best["rows"]) and best["rows"][0]["price"] is not None
            next(lg for lg in reversed(legs) if lg["kind"] == "flight")["used"] = priced
            if priced:
                fl_total += best["rows"][0]["price"]
            if best["post"]:
                lg = _ground_leg(airport_point(best["dst"]), h["to_pt"], h["date"], f"{best['dst']['iata']} airport",
                                 h["to_name"], h["to_idx"], currency)
                legs.append(lg)
                g_lo, g_hi = _gadd(g_lo, g_hi, lg["ground"])
            rl = _rail_for(h, ends, rails, by_train, pace)
            if rl:
                legs.append(rl)
                road = _ground_leg(h.get("from_pt") or home, h.get("to_pt") or home, h["date"], rl["from_name"],
                                   rl["to_name"], h["to_idx"], currency)
                if road["ground"].get("mode") == "road" and road["ground"]["hours"][0] <= rail_max:
                    road["alt"] = True  # shown beside rail and flights, never added to the totals
                    legs.append(road)
            if not priced:  # totals use the cheapest option that fits the brief; a rail fare is never invented
                if rl and rl["rows"]:
                    rl["used"] = True
                    rail_missing += 1
                else:
                    fl_missing += 1

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
                             "places": {"diet": pl.get("diet", {}), "sights": pl.get("sights", []),
                                        "nightlife": pl.get("nightlife", []) if night_on else []},
                             "places_sources": pl.get("sources", []),
                             "stays": cands, "stay_ok": bool(cands),
                             "stay_error": None if cands else (r.error if r else "not fetched"),
                             "stay_backend": getattr(r, "backend", "none") if r else "none",
                             "stay_fetched": _fmt_ts(r.fetched_at) if r and r.ok else None,
                             "stay_url": r.source_url if r else "", "stay_shot": r.screenshot_path if r else None,
                             "rooms": (rr.data["ranked"][:2] if rr and rr.ok else [])})
        days = o["nights"] + 1
        party_n = sum(math.ceil(s["nights"] * cfg["party_share"]) for s in o["stops"]) if night_on else 0
        spend_rows, spend_pp, spend_note = daily_spend(cfg, days, party_n, night_on)
        o2 = {**o, "legs": legs, "stops": stop_out}
        o2.pop("hops", None)
        o2["totals"] = {"flights_pp": fl_total, "flight_legs_missing": fl_missing, "rail_fares_missing": rail_missing, "stays_total": st_total,
                        "stays_pp": round(st_total / people), "stays_missing": st_missing,
                        "ground_lo_pp": g_lo, "ground_hi_pp": g_hi, "days": days, "party_nights": party_n,
                        "spend_rows": spend_rows, "spend_pp": spend_pp, "spend_note": spend_note,
                        "core_pp": fl_total + round(st_total / people),
                        "all_in_lo_pp": fl_total + round(st_total / people) + g_lo + (spend_pp or 0),
                        "all_in_hi_pp": fl_total + round(st_total / people) + g_hi + (spend_pp or 0)}
        o2["days_plan"] = build_days(o2, {s["name"]: s["places"] for s in stop_out}, prefs, pace, night_on)
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
    for cc, res in hol.items():
        # a domestic trip's one country is both: leave planning at home and closures where you travel
        role = ("both" if cc in ccs else "home") if cc == home_ap["cc"] else "destination"
        ev_rows += events.holiday_rows(res, AP.countries().get(cc, cc), role)
    if cfg.get("destination"):  # region-level festival mentions, split into one event each
        fw = events.wikipedia_festivals(str(cfg["destination"]).split(",")[0].strip(), win_s, win_e)
        ev_rows += [dict(r, date=None) for r in (fw.data if fw.ok else [])]
    for st in stops:  # each stop's own Events / Festivals section (guide text, dated by the month it names)
        w = wikivoyage(st["name"])
        if w.ok:
            ev_rows += [dict(r, date=None) for r in events.section_mentions(
                w.data.get("text", ""), win_s, win_e, "wikivoyage " + st["name"], w.source_url)]
    ev_rows.sort(key=lambda r: r.get("date") or "9999")
    for cc, r in hol.items():
        ev.append({"label": f"public holidays {cc}", "ok": r.ok, "url": r.source_url, "file": None,
                   "fetched_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(r.fetched_at)), "error": r.error,
                   "cached": bool(getattr(r, "cached", False))})

    # ---- sections that do not apply to this trip, listed once so the reader knows they were considered
    na = []
    domestic = all(cc == home_ap["cc"] for cc in ccs)
    if domestic:
        na += ["visa: domestic trip (every stop is in the home country)",
               "safety advisory: domestic trip", "FX: domestic trip, one currency"]
    else:
        if not visa:
            na.append("visa: every destination is the passport's own country")
        if not fx:
            na.append("FX: the destination uses the same currency as the trip")
    all_ground = all(lg["kind"] == "ground" for lg in out_opts[0]["legs"]) if out_opts and out_opts[0]["legs"] else False
    if all_ground:
        na.append(f"flights: every hop is within {cfg['max_ground_hours']} h by road, so ground legs replace flights "
                  "(a rental car may suit this route; check local rental sites)")
    backends = {"flights": sorted({getattr(v, "backend", "none") for v in flights.values()}),
                "stays": sorted({getattr(v, "backend", "none") for v in stays.values()})}
    return {
        "meta": {"home": home["iata"], "home_name": home["name"], "people": people, "budget_night": budget or None,
                 "has_flights": any(lg["kind"] == "flight" for o in out_opts for lg in o["legs"]),
                 "prefs": prefs, "currency": currency, "budget_set": bool(budget), "passport": cfg["passport"],
                 "generated": time.strftime("%d %b %Y %H:%M"), "browser": cfg["browser"],
                 "title": " + ".join(s["name"] for s in stops), "end_airport": end_pt["iata"],
                 "rates": {k: cfg.get(k) for k in ("meal_rate", "meals_per_day", "party_rate", "party_share", "transport_day")},
                 "backends": backends, "cache": cache.stats(), "wall_s": round(time.time() - t0, 1)},
        "options": out_opts,
        "events": ev_rows,
        "fx": {k: v.data for k, v in fx.items() if v.ok},
        "advisory": {cc: (r.data | {"url": r.source_url}) if r.ok else {"error": r.error, "entries": (r.data or {}).get("entries", [])}
                     for cc, r in adv.items()},
        "climate": {k: (r.data | {"url": r.source_url}) if r.ok else {"error": r.error} for k, r in clim.items()},
        "not_applicable": na,
        "weather": {k: (r.data if r.ok else {"error": r.error}) for k, r in wx.items()},
        "visa": {cc: (r.data | {"source": r.source_url, "fetched": _fmt_ts(r.fetched_at)}) if r.ok
                 else {"error": r.error, "source": r.source_url} for cc, r in visa.items()},
        "countries": cnames,
        "photos": {k: (r.data if r.ok else []) for k, r in photos.items()},
        "evidence": ev,
    }
