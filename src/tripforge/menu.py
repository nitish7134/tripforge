"""Options menu for any country/region: candidate stops + route combos, everything tagged live/est.

No LLM: candidates come from the Wikivoyage article's Cities/Other destinations lists, vibe fit is a
keyword score of each stop's article against the brief's prefs, prices are live fli/pyairbnb where
fetchable and labelled est otherwise. Writes menu.md, menu.json and variants.md next to the brief.
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import cache, events, ground
from .fetchers import airports as AP
from .fetchers import flights_fli as FL
from .fetchers.places import wikivoyage
from .stops import StopError, resolve

VIBE = {"party": r"nightlife|party|parties|club|bar|full moon|rave|pub crawl",
        "veg": r"vegetarian|vegan|indian restaurant|\bveg\b",
        "beach": r"beach|snorkel|island|dive|diving",
        "culture": r"temple|museum|palace|old town|heritage|cathedral|market",
        "nature": r"hike|hiking|waterfall|national park|trek|jungle|mountain",
        "food": r"street food|food market|cuisine|restaurant"}


def _window(cfg: dict) -> tuple[dt.date, dt.date]:
    if cfg.get("start"):
        s = dt.date.fromisoformat(str(cfg["start"]))
    else:
        y, m = str(cfg.get("month", dt.date.today().strftime("%Y-%m"))).split("-")[:2]
        s = dt.date(int(y), int(m), 1)
    return s, s + dt.timedelta(days=int(cfg.get("nights", 10)))


def _fit(text: str, prefs: list[str]) -> dict:
    out = {}
    for p in prefs:
        rx = VIBE.get(p, re.escape(p))
        out[p] = len(re.findall(rx, text, re.I))
    return out


def _candidate(d: dict, country: str, prefs: list[str], home: str, start: dt.date, live: bool) -> dict | None:
    wv = wikivoyage(d["page"])
    if not wv.ok:
        return None
    text = wv.data.get("text", "")
    try:
        s = resolve(d["name"], country)
    except StopError:
        return None
    fit = _fit(text, prefs)
    musts = [i for i in wv.data["items"] if i["kind"] in ("see", "do")]
    musts.sort(key=lambda i: (not i.get("price"), i["kind"] != "see"))
    fl = None
    if live and s["iata"] != home:
        r = cache.cached("flights:fli", {"o": home, "d": s["iata"], "date": start.isoformat(), "ccy": "INR", "v": 1},
                         lambda: FL.fetch_leg(home, s["iata"], start.isoformat()))
        priced = [x for x in (r.data or []) if x.get("price")] if r.ok else []
        fl = priced[0] if priced else None
    acc = ground.estimate({"name": s["airport_city"], "iata": s["iata"], "is_airport": True,
                           "lat": s["airport_lat"], "lon": s["airport_lon"]}, s) if s["airport_km"] > 40 else None
    nights = 2 + min(2, len(musts) // 6)
    return {"name": d["name"], "page": d["page"], "kind": d["kind"], "blurb": d["blurb"] or wv.data["lead"][:180],
            "lat": s["lat"], "lon": s["lon"], "cc": s["cc"], "iata": s["iata"], "airport_km": s["airport_km"],
            "island": s.get("island", False), "fit": fit, "fit_score": sum(min(v, 15) for v in fit.values()),
            "nights": nights, "musts": [{"name": m["name"], "fee": m.get("price") or "fee not listed",
                                         "blurb": m["blurb"]} for m in musts[:5]],
            "flight": fl, "access": acc, "url": wv.source_url,
            "events": events.mentions(text, start, start + dt.timedelta(days=40), "wikivoyage", wv.source_url, 3),
            "full_moon_text": "full moon" in text.lower()}


def _verdict(c: dict, prefs: list[str]) -> tuple[str, str]:
    top = max(c["fit"].items(), key=lambda kv: kv[1])[0] if c["fit"] else None
    worth = f"worth it for {top} ({c['fit'][top]} mentions)" if top and c["fit"][top] else "worth it as a change of pace"
    weak = [p for p, v in c["fit"].items() if v == 0]
    skip = (f"skip if {', '.join(weak)} matters most" if weak else "skip if short on time") + (
        f"; no airport within {c['airport_km']} km, costs a transfer day" if c["airport_km"] > 60 else "")
    return worth, skip


def _route_cost(order: list[dict], home: str, ppl: int) -> dict:
    g = 0
    out_f, back_f = order[0]["flight"], order[-1]["flight"]
    # Return fare assumed ~ the outbound fare to the last stop's airport (est). Missing either -> unavailable.
    fl = (out_f["price"] + back_f["price"]) if out_f and back_f else None
    for a, b in zip(order, order[1:]):
        if ground.needs_ground(a, b):
            g += sum(ground.estimate(a, b)["inr"]) / 2
        else:
            near = [c["flight"]["price"] for c in (a, b) if c["flight"]]
            g += (min(near) / 3) if near else 0  # domestic hop ~ a third of the long-haul fare (est)
    stays = sum((c.get("stay_pn") or 0) * c["nights"] for c in order) / ppl
    return {"flights_pp": None if fl is None else round(fl), "ground_pp": round(g), "stays_pp": round(stays),
            "core_pp": None if fl is None else round(fl + g + stays),
            "tag": "est (outbound live, return and hops estimated)" if fl is not None else "flights unavailable"}


def run_menu(cfg: dict, out_dir: Path, live: bool = True, n: int = 10) -> tuple[Path, Path]:
    dest = cfg.get("destination") or cfg.get("country")
    if not dest:
        raise SystemExit("brief needs destination (country or region)")
    home = str(cfg.get("from", "BLR")).upper()
    prefs = cfg.get("prefs") or []
    prefs = [p.strip().lower() for p in (prefs.split(",") if isinstance(prefs, str) else prefs)]
    ppl, nights = int(cfg.get("people", 2)), int(cfg.get("nights", 10))
    budget = int(cfg.get("budget_night", 5000))
    meal, party = int(cfg.get("meal_rate", 1000)), int(cfg.get("party_rate", 2500))
    start, end = _window(cfg)
    top = wikivoyage(dest)
    if not top.ok:
        raise SystemExit(f"no Wikivoyage article for {dest}: {top.error}")
    allds = top.data["destinations"]
    cities = [d for d in allds if d["kind"] == "city"]
    others = [d for d in allds if d["kind"] == "destination"]
    half = n // 2 + 2
    dests = cities[:half] + others[:half]
    with ThreadPoolExecutor(6) as ex:
        cands = [c for c in ex.map(lambda d: _candidate(d, dest, prefs, home, start, live), dests) if c]
    cands.sort(key=lambda c: -c["fit_score"])
    cands = cands[:n]
    # Stay price: live pyairbnb for the top few, the median of those as est for the rest.
    if live:
        from .plan import fetch_stay
        def st(c):
            s = resolve(c["name"], dest)
            s["nights"] = c["nights"]
            cin, cout = start.isoformat(), (start + dt.timedelta(days=c["nights"])).isoformat()
            r = fetch_stay(s, cin, cout, ppl, budget, "INR", "pyairbnb", lambda: None)
            return r.data["ranked"][0]["per_night"] if r.ok else None
        with ThreadPoolExecutor(3) as ex:
            for c, pn in zip(cands[:6], ex.map(st, cands[:6])):
                c["stay_pn"], c["stay_tag"] = pn, "live" if pn else None
    known = [c["stay_pn"] for c in cands if c.get("stay_pn")]
    med = round(statistics.median(known)) if known else None
    for c in cands:
        if not c.get("stay_pn"):
            c["stay_pn"], c["stay_tag"] = med, ("est (median of live)" if med else "unavailable")
        c["worth"], c["skip"] = _verdict(c, prefs)
    moon = events.lunar_rows(start, end, ["full moon"] if any(c["full_moon_text"] for c in cands) else [])
    fest = events.wikipedia_festivals(dest, start, end)
    # combos: pick k stops whose nights fit, ordered by a nearest-neighbour walk
    combos = []
    for k in (2, 3, 4):
        for combo in itertools.combinations(cands[:7], k):
            if sum(c["nights"] for c in combo) > nights + 1:
                continue
            order = [max(combo, key=lambda c: bool(c["flight"]))]
            rest = [c for c in combo if c is not order[0]]
            while rest:
                nxt = min(rest, key=lambda c: AP.km(order[-1]["lat"], order[-1]["lon"], c["lat"], c["lon"]))
                order.append(nxt)
                rest.remove(nxt)
            extra = nights - sum(c["nights"] for c in order)
            for i in range(max(extra, 0)):
                order[i % len(order)] = dict(order[i % len(order)], nights=order[i % len(order)]["nights"] + 1)
            cost = _route_cost(order, home, ppl)
            combos.append({"stops": [c["name"] for c in order], "nights": [c["nights"] for c in order],
                           "fit": sum(c["fit_score"] for c in order), "cost": cost,
                           "stops_spec": ",".join(f"{c['name']}:{c['nights']}" for c in order)})
    picks, seen = [], set()
    INF = float("inf")
    cp = lambda x: INF if x["cost"]["core_pp"] is None else x["cost"]["core_pp"]  # noqa: E731
    for key in (lambda x: (cp(x) == INF, -x["fit"]), cp, lambda x: (cp(x) == INF, len(x["stops"]), -x["fit"]),
                lambda x: (cp(x) == INF, -x["fit"] / max(cp(x), 1))):
        for c in sorted(combos, key=key):
            if c["stops_spec"] not in seen:
                seen.add(c["stops_spec"])
                picks.append(c)
                break
    label = ["best vibe fit", "cheapest core", "fewest moves", "best fit per rupee"]
    for p, lb in zip(picks, label):
        p["why"] = lb
    days = nights + 1
    spend = {"meals": days * 3 * meal, "party": (sum(1 for _ in range(nights // 2)) * party) if "party" in prefs else 0}
    data = {"destination": dest, "window": {"start": start.isoformat(), "end": end.isoformat()}, "prefs": prefs,
            "rates": {"meal_rate": meal, "party_rate": party}, "spend_pp_est": spend, "candidates": cands,
            "combos": picks, "events": moon + (fest.data if fest.ok else []), "source": top.source_url}
    out_dir.mkdir(parents=True, exist_ok=True)
    js = out_dir / "menu.json"
    js.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str))
    md = out_dir / "menu.md"
    md.write_text(_md(data, home))
    (out_dir / "variants.md").write_text(_variants(data))
    return md, js


def _money(n):
    return "unavailable" if n is None else f"₹{int(n):,}"


def _md(d: dict, home: str) -> str:
    L = [f"# {d['destination']} options menu ({d['window']['start']} to {d['window']['end']})", "",
         f"Prefs: {', '.join(d['prefs']) or 'none'}. Rates: {_money(d['rates']['meal_rate'])}/meal, "
         f"{_money(d['rates']['party_rate'])}/party night. Tags: live = fetched now, est = estimate. "
         f"Candidates from [Wikivoyage]({d['source']}); community suggestions, not endorsements.", "",
         "## Candidate stops", ""]
    for c in d["candidates"]:
        fl = c["flight"]
        get = (f"{fl['flight']} {home}->{c['iata']} {fl['dep']} {_money(fl['price'])} (live, nonstop)" if fl
               else f"fly to {c['iata']}: no nonstop priced from {home} (unavailable)")
        if c["access"]:
            a = c["access"]
            get += f" + {a['mode']} {a['hours'][0]}-{a['hours'][1]}h {_money(a['inr'][0])}-{_money(a['inr'][1])} (est)"
        L += [f"### {c['name']} ({c['kind']}) -- fit {c['fit_score']}", "", c["blurb"], "",
              f"- Vibe fit: {', '.join(f'{k} {v}' for k, v in c['fit'].items()) or 'n/a'} (mentions in the article)",
              f"- Suggested nights: {c['nights']}",
              f"- Stay: {_money(c['stay_pn'])}/night ({c['stay_tag']}); includes the Airbnb nightly price for an entire "
              f"place, excludes service/cleaning fees shown at checkout, food and transfers",
              f"- Getting there: {get}",
              "- Must-dos: " + ("; ".join(f"{m['name']} ({m['fee']})" for m in c["musts"]) or "none listed"),
              f"- {c['worth'].capitalize()}; {c['skip']}"]
        for e in c["events"]:
            L.append(f"- Event mention: {e['text']} ([source]({e['url']}))")
        L += [f"- [Wikivoyage]({c['url']})", ""]
    L += ["## Events in the window", ""]
    L += [f"- {e['text']} ({e['tag']}{', ' + e['url'] if e.get('url') else ''})" for e in d["events"]] or ["- none found"]
    L += ["", "## Route combos", ""]
    for i, c in enumerate(d["combos"], 1):
        k = c["cost"]
        L.append(f"{i}. **{' -> '.join(f'{s} {n}N' for s, n in zip(c['stops'], c['nights']))}** ({c['why']}): "
                 f"core {_money(k['core_pp'])}/person = flights {_money(k['flights_pp'])} + hops {_money(k['ground_pp'])} "
                 f"+ stays {_money(k['stays_pp'])} [{k['tag']}]. `--stops \"{c['stops_spec']}\"`")
    s = d["spend_pp_est"]
    L += ["", f"Daily spend on top (est, your rates): meals {_money(s['meals'])} + party {_money(s['party'])} per person.", ""]
    return "\n".join(L)


def _variants(d: dict) -> str:
    L = [f"# Route variants for {d['destination']} (community suggestions)", ""]
    for i, c in enumerate(d["combos"], 1):
        L.append(f"{i}. {c['stops_spec']} -- {c['why']}, core {_money(c['cost']['core_pp'])}/person ({c['cost']['tag']})")
    return "\n".join(L) + "\n"
