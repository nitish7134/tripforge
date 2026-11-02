"""Ground legs (road, ferry) between any two points, resolved at runtime. No tables, no fare bands.

WHAT is fetched and HOW:
- mode + duration: OSRM public routing (keyless). A road route -> mode "road" with OSRM's driving duration.
  No road route, or an endpoint that only snaps to a road far away (water between) -> mode "ferry", duration
  from straight-line distance / FERRY_KMH, flagged "no road route". Cached 7 days.
- fare: a live read of the 12Go route page ("from X" floor) converted to the trip currency; when the page gives
  no result the fare is None and the row links to the 12Go page. A heuristic may produce DURATION, never money.
- rail: the destination's Wikivoyage "Get in" text is checked for train/rail mentions -> a note, never a fare.
"""
from __future__ import annotations

import re
import unicodedata

from . import cache, money
from .fetchers.airports import km
from .fetchers.common import Result, client, fail

OSRM = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
GO12 = "https://12go.asia/en/travel/{a}/{b}"
FERRY_KMH = 30
ROAD_FACTOR = 1.25  # straight line -> road, only used to decide "road or flight" and as the duration fallback
ROAD_KMH_FALLBACK = 60  # only when OSRM is unreachable: a duration, never money
SNAP_MAX_M = 3000  # an endpoint snapping further than this from the nearest road has no road access
INDIRECT_RATIO = 3.0  # road route this many times the straight line: the water is in the way
# A stop-to-stop hop at or under this road distance is ground, not a flight (overridable via the brief).
GROUND_MAX_KM = 350


def road_km(a: dict, b: dict) -> float:
    return km(a["lat"], a["lon"], b["lat"], b["lon"]) * ROAD_FACTOR


def needs_ground(a: dict, b: dict, max_km: float = GROUND_MAX_KM) -> bool:
    """True when a stop-to-stop hop is short enough to go by road or ferry rather than fly."""
    return road_km(a, b) <= max_km


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def route(a: dict, b: dict) -> Result:
    """OSRM driving route: data {duration_h, distance_km, snap_m: [m, m]} or ok=False when no road route."""
    url = OSRM.format(lon1=a["lon"], lat1=a["lat"], lon2=b["lon"], lat2=b["lat"])

    def go() -> Result:
        try:
            with client(20) as c:
                j = c.get(url).json()
        except Exception as e:  # noqa: BLE001
            return fail(f"osrm unreachable: {type(e).__name__}", url)
        if j.get("code") != "Ok" or not j.get("routes"):
            return Result(ok=True, data={"no_route": True}, source_url=url)  # a real answer: water between
        r = j["routes"][0]
        return Result(ok=True, data={"duration_h": r["duration"] / 3600, "distance_km": r["distance"] / 1000,
                                     "snap_m": [w.get("distance", 0) for w in j.get("waypoints", [])]}, source_url=url)
    return cache.cached("ground:osrm", {"u": url}, go)


_FROM = re.compile(r"from\s*([^\sA-Za-z\d]{1,3}|[A-Z]{3})\s?([\d][\d,\.]*)", re.I)


def _fare_ccy(sym: str) -> str | None:
    if re.fullmatch(r"[A-Za-z]{3}", sym):
        return sym.upper()
    hits = [c for c, s in money.SYMBOLS.items() if s.strip() == sym]
    return hits[0] if len(hits) == 1 else None  # an ambiguous symbol ($, kr) is not guessed


def fare(a_name: str, b_name: str, currency: str) -> Result:
    """Cheapest listed fare 'from X' on the 12Go route page, converted to `currency`. ok=False when none."""
    url = GO12.format(a=_slug(a_name), b=_slug(b_name))

    def go() -> Result:
        try:
            with client(20) as c:
                r = c.get(url, headers={"Accept-Language": "en"})
            if r.status_code != 200 or not r.text.strip():
                return fail(f"12go returned HTTP {r.status_code} with no result", url)
            m = _FROM.search(re.sub(r"<[^>]+>", " ", r.text))
            if not m:
                return fail("12go page lists no fare", url)
            src = _fare_ccy(m.group(1))
            if not src:
                return fail(f"12go fare symbol {m.group(1)!r} is ambiguous", url)
            amt = float(m.group(2).replace(",", ""))
            k = money.rate(src, currency)
            if k is None:
                return fail("fx rate unavailable", url)
            return Result(ok=True, data={"from": round(amt * k), "currency": currency.upper()}, source_url=url)
        except Exception as e:  # noqa: BLE001
            return fail(f"12go error: {type(e).__name__}", url)
    return cache.cached("ground:12go", {"u": url, "c": currency.upper()}, go)


def rail_note(b_name: str) -> str | None:
    """Wikivoyage 'Get in' of the destination mentions trains -> a pointer, never a fare."""
    from .fetchers.places import wikivoyage
    w = wikivoyage(b_name)
    if not w.ok:
        return None
    m = re.search(r"==\s*Get in\s*==(.*?)(?=\n==[^=]|\Z)", w.data.get("text", ""), re.S)
    if m and re.search(r"\b(train|rail|railway)\b", m.group(1), re.I):
        return "rail may exist (see the Wikivoyage 'Get in' section), check the operator"
    return None


def estimate(a: dict, b: dict, currency: str) -> dict:
    """{'mode','hours':[lo,hi],'amount':[lo,hi]|None,'currency','km','source','note','link'}.
    `amount` is only ever a live fare read; None means 'fare unavailable'."""
    d = road_km(a, b)
    r = route(a, b)
    out = {"currency": currency.upper(), "amount": None, "km": round(d), "note": None,
           "link": GO12.format(a=_slug(a["name"]), b=_slug(b["name"]))}
    straight = d / ROAD_FACTOR
    if r.ok and r.data and not r.data.get("no_route"):
        dd = r.data
        water = max(dd["snap_m"] or [0]) > SNAP_MAX_M or dd["distance_km"] > INDIRECT_RATIO * max(straight, 1)
        if not water:
            h = dd["duration_h"] + 0.3
            out.update(mode="road", hours=[round(h * 0.9, 1), round(h * 1.3, 1)], km=round(dd["distance_km"]),
                       source="osrm")
        else:
            out.update(_ferry(straight), source="osrm (no road route)")
    elif r.ok:
        out.update(_ferry(straight), source="osrm (no road route)")
    else:  # OSRM down: a duration estimate only
        h = d / ROAD_KMH_FALLBACK + 0.3
        out.update(mode="road or rail", hours=[round(h * 0.9, 1), round(h * 1.3, 1)], source="distance estimate")
    f = fare(a["name"], b["name"], currency)
    if f.ok:
        out["amount"] = [f.data["from"], f.data["from"]]
        out["fare_note"] = "cheapest listed fare on 12Go"
    out["fare_url"] = f.source_url
    out["note"] = rail_note(b["name"])
    return out


def _ferry(straight_km: float) -> dict:
    h = straight_km / FERRY_KMH + 0.5
    return {"mode": "ferry", "hours": [round(h * 0.9, 1), round(h * 1.3, 1)]}


def mid(g: dict) -> float:
    return sum(g["amount"]) / 2 if g.get("amount") else 0.0
