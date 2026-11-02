"""Plan orchestration: stops -> legs/dates -> fetchers -> plan dict."""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.console import Console

from .browser import make_browser
from .fetchers import flights as F
from .fetchers import stays as S
from .fetchers.common import Result, fail
from .fetchers.misc import fetch_advisories, fetch_climate, fetch_fx, fetch_weather, load, visa_for
from .fetchers.photos import fetch_photos

console = Console(stderr=True)


class PlanError(ValueError):
    pass


def parse_stops(spec: str, places: dict) -> list[dict]:
    """'Phuket:2,Krabi:3@KBV,Bangkok:5' -> [{name,nights,iata,cc,lat,lon,airbnb,...}]"""
    stops = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        m = re.match(r"^(?P<name>[^:@]+?)\s*(?::\s*(?P<n>\d+))?\s*(?:@(?P<iata>[A-Za-z]{3}))?$", part)
        if not m:
            raise PlanError(f"cannot parse stop {part!r}; use Name:nights[@IATA]")
        key = m["name"].strip().lower()
        city = places["cities"].get(key)
        if not city:
            raise PlanError(f"unknown destination {m['name']!r}. Known: {', '.join(sorted(c['name'] for c in places['cities'].values()))}. "
                            "Add it to src/tripforge/data/places.json.")
        s = dict(city)
        if m["iata"]:
            s["iata"] = m["iata"].upper()
        s["nights"] = int(m["n"] or 2)
        stops.append(s)
    if not stops:
        raise PlanError("no stops given")
    return stops


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


# City pairs normally travelled by road or ferry; no flight search is attempted.
GROUND_PAIRS = {frozenset(x) for x in (("HKT", "KBV"), ("HKT", "USM"), ("KUL", "PEN"), ("HAN", "DAD"))}


def build_option(home: str, stops: list[dict], start: str) -> dict:
    d = _d(start)
    legs, prev, prev_name, prev_cc = [], home, None, None
    out_stops = []
    for i, s in enumerate(stops):
        legs.append({"orig": prev, "dest": s["iata"], "date": d.isoformat(),
                     "from_name": prev_name, "to_name": s["name"]})
        cin, cout = d, d + dt.timedelta(days=s["nights"])
        out_stops.append({**s, "checkin": cin.isoformat(), "checkout": cout.isoformat()})
        prev, prev_name, d = s["iata"], s["name"], cout
    legs.append({"orig": prev, "dest": home, "date": d.isoformat(), "from_name": prev_name, "to_name": "home"})
    for lg in legs:
        lg["kind"] = "ground" if (lg["orig"] == lg["dest"] or frozenset((lg["orig"], lg["dest"])) in GROUND_PAIRS) else "flight"
    return {"start": start, "end": d.isoformat(), "nights": sum(s["nights"] for s in stops),
            "legs": legs, "stops": out_stops}


def _unavail(msg):
    return fail(msg)


def run_plan(*, home: str, stops_spec: str, starts: list[str], people: int, budget_night: int, prefs: list[str],
             currency: str, passport: str, out: Path, browser_mode: str, hostels: bool) -> dict:
    places = load("places.json")
    stops = parse_stops(stops_spec, places)
    home = home.upper()
    if home not in places["airports"]:
        raise PlanError(f"unknown home airport {home}. Known: {', '.join(places['airports'])}")
    evid, cache = out / "evidence", out / "cache"
    evid.mkdir(parents=True, exist_ok=True)
    (cache / "photos").mkdir(parents=True, exist_ok=True)
    options = [build_option(home, stops, s) for s in starts]
    results: list[Result] = []

    def keep(r: Result, label: str) -> Result:
        results.append(r)
        r.data = r.data  # noqa: PLW0127
        setattr(r, "label", label)
        return r

    # ---- keyless fetchers (parallel)
    countries = load("places.json")["countries"]
    ccs = sorted({s["cc"] for s in stops})
    spend_ccys = sorted({countries[cc]["spend_ccy"] for cc in ccs if cc in countries} - {currency})
    first_month = _d(starts[0]).month
    console.print("[bold]keyless fetchers[/bold] (fx, advisory, climate, weather, visa, photos)")
    with ThreadPoolExecutor(max_workers=8) as ex:
        fx_f = {c: ex.submit(fetch_fx, c, currency, evid) for c in spend_ccys}
        adv_f = ex.submit(fetch_advisories, {cc: countries[cc]["name"] for cc in ccs if cc in countries}, evid)
        clim_f = {s["name"]: ex.submit(fetch_climate, s["iata"], _d(o["start"]).month, evid)
                  for s in stops for o in options[:1]}
        wx_f = {s["name"]: ex.submit(fetch_weather, s["lat"], s["lon"], starts[0], options[0]["end"], evid, s["name"])
                for s in stops}
        ph_f = {s["name"]: ex.submit(fetch_photos, f"{s['name']} {countries.get(s['cc'], {}).get('name', '')}", 2,
                                      cache / "photos") for s in stops}
        fx = {c: f.result() for c, f in fx_f.items()}
        adv = adv_f.result()
        clim = {k: f.result() for k, f in clim_f.items()}
        wx = {k: f.result() for k, f in wx_f.items()}
        photos = {k: f.result() for k, f in ph_f.items()}
    visa = {cc: visa_for(passport, cc) for cc in ccs}

    # ---- browser fetchers (sequential, one browser)
    flight_res: dict[tuple, Result] = {}
    stay_res: dict[tuple, Result] = {}
    room_res: dict[tuple, Result] = {}
    need_f = {(lg["orig"], lg["dest"], lg["date"]) for o in options for lg in o["legs"] if lg["kind"] == "flight"}
    need_s = {(s["name"], s["airbnb"], s["checkin"], s["checkout"], s["nights"]) for o in options for s in o["stops"]}
    console.print(f"[bold]browser fetchers[/bold] mode={browser_mode}: {len(need_f)} flight legs, {len(need_s)} stay searches")
    try:
        with make_browser(browser_mode) as br:
            for (o_, d_, date) in sorted(need_f, key=lambda x: x[2]):
                console.print(f"  flights {o_}->{d_} {date}")
                flight_res[(o_, d_, date)] = F.fetch_leg(br, o_, d_, date, currency, evid)
                console.print(f"    -> {'ok ' + str(len(flight_res[(o_, d_, date)].data)) if flight_res[(o_, d_, date)].ok else flight_res[(o_, d_, date)].error}")
            for (name, slug, cin, cout, n) in sorted(need_s, key=lambda x: x[2]):
                console.print(f"  stays {name} {cin}..{cout}")
                stay_res[(name, cin)] = S.fetch_stay(br, slug, cin, cout, n, people, budget_night, currency,
                                                     evid, name.replace(" ", ""))
                console.print(f"    -> {'ok ' + str(len(stay_res[(name, cin)].data['ranked'])) if stay_res[(name, cin)].ok else stay_res[(name, cin)].error}")
                if hostels:
                    room_res[(name, cin)] = S.fetch_stay(br, slug, cin, cout, n, people, max(int(budget_night * 0.4), 500),
                                                         currency, evid, name.replace(" ", "") + "_rooms", "Private room")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]browser unavailable: {e}[/red]")
        for k in need_f:
            flight_res.setdefault(k, fail(f"browser unavailable: {e}"))
        for (name, _s, cin, _c, _n) in need_s:
            stay_res.setdefault((name, cin), fail(f"browser unavailable: {e}"))

    # ---- assemble
    fx_rate = lambda ccy: 1.0 if ccy == currency else (fx[ccy].data["rate"] if fx.get(ccy) and fx[ccy].ok else None)  # noqa: E731
    out_opts = []
    for o in options:
        flights_total, missing = 0, 0
        legs = []
        for lg in o["legs"]:
            if lg["kind"] == "ground":
                legs.append({**lg, "rows": [], "note": "ground transfer", "ok": False})
                continue
            r = flight_res.get((lg["orig"], lg["dest"], lg["date"]))
            rows = (r.data or [])[:3] if r and r.ok else []
            if rows:
                flights_total += rows[0]["price"]
            else:
                missing += 1
            legs.append({**lg, "rows": rows, "ok": bool(rows), "source_url": r.source_url if r else "",
                         "screenshot": r.screenshot_path if r else None,
                         "error": None if rows else (r.error if r else "not fetched")})
        stays_total, stays_missing = 0, 0
        stop_out = []
        for s in o["stops"]:
            r = stay_res.get((s["name"], s["checkin"]))
            cands = r.data["ranked"][:3] if r and r.ok else []
            if cands:
                stays_total += cands[0]["total"]
            else:
                stays_missing += 1
            rr = room_res.get((s["name"], s["checkin"]))
            nights = s["nights"]
            stop_out.append({**{k: s[k] for k in ("name", "iata", "cc", "nights", "checkin", "checkout")},
                             "areas": s.get("areas") or [], "highlights": s.get("highlights") or [],
                             "stays": cands, "stay_ok": bool(cands), "stay_error": None if cands else (r.error if r else "not fetched"),
                             "stay_url": r.source_url if r else "", "stay_shot": r.screenshot_path if r else None,
                             "rooms": (rr.data["ranked"][:2] if rr and rr.ok else []),
                             "per_night_budget_ok": bool(cands) and cands[0]["per_night"] <= budget_night * 1.15,
                             "nights_n": nights})
        # spend estimates
        days = o["nights"] + 1
        lo = hi = 0.0
        spend_rows, spend_ok = [], True
        for cc in ccs:
            c = countries.get(cc)
            if not c or not c["spend"]:
                continue
            rate = fx_rate(c["spend_ccy"])
            if rate is None:
                spend_ok = False
                continue
            share = sum(s["nights"] for s in o["stops"] if s["cc"] == cc) / max(o["nights"], 1)
            for k, (a, b) in c["spend"].items():
                spend_rows.append({"label": f"{k} ({c['name']})", "lo": round(a * rate), "hi": round(b * rate)})
                lo += a * rate * days * share
                hi += b * rate * days * share
        out_opts.append({**o, "legs": legs, "stops": stop_out,
                         "totals": {"flights_pp": flights_total, "flight_legs_missing": missing,
                                    "stays_total": stays_total, "stays_pp": round(stays_total / people),
                                    "stays_missing": stays_missing,
                                    "spend_lo_pp": round(lo) if spend_ok else None, "spend_hi_pp": round(hi) if spend_ok else None,
                                    "days": days, "spend_rows": spend_rows,
                                    "core_pp": flights_total + round(stays_total / people)}})

    ev = []
    for label, r in ([(f"flights {k[0]}-{k[1]} {k[2]}", v) for k, v in flight_res.items()] +
                     [(f"stays {k[0]} {k[1]}", v) for k, v in stay_res.items()] +
                     [(f"fx {k}", v) for k, v in fx.items()] + [(f"advisory {k}", v) for k, v in adv.items()] +
                     [(f"climate {k}", v) for k, v in clim.items()] + [(f"visa {k}", v) for k, v in visa.items()]):
        ev.append({"label": label, "ok": r.ok, "url": r.source_url,
                   "file": Path(r.screenshot_path).name if r.screenshot_path else None,
                   "fetched_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(r.fetched_at)), "error": r.error})

    return {
        "meta": {"home": home, "home_name": places["airports"][home][0], "people": people, "budget_night": budget_night,
                 "prefs": prefs, "currency": currency, "passport": passport,
                 "generated": time.strftime("%d %b %Y %H:%M"), "browser": browser_mode,
                 "title": " + ".join(s["name"] for s in stops)},
        "options": out_opts,
        "fx": {k: v.data for k, v in fx.items() if v.ok},
        "advisory": {cc: (r.data | {"url": r.source_url}) if r.ok else {"error": r.error} for cc, r in adv.items()},
        "climate": {k: (r.data | {"url": r.source_url}) if r.ok else {"error": r.error} for k, r in clim.items()},
        "weather": {k: (r.data if r.ok else {"error": r.error}) for k, r in wx.items()},
        "visa": {cc: (r.data | {"source": r.source_url}) if r.ok else {"error": r.error} for cc, r in visa.items()},
        "countries": {cc: countries[cc]["name"] for cc in ccs},
        "photos": {k: (r.data if r.ok else []) for k, r in photos.items()},
        "evidence": ev,
    }
