"""Indicative ground legs (van, bus, rail, ferry) between any two points.

A table entry in data/ground.json wins; otherwise a distance heuristic produces a labelled
"indicative" estimate. Nothing here is a fetched price. Amounts come back in the trip currency.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import money
from .fetchers.airports import km

DATA = Path(__file__).resolve().parent / "data" / "ground.json"
ISLAND = re.compile(r"\b(koh|ko|isla|ilha|island|isle|nusa|pulau|ile|île|insel|isola)\b", re.I)

# Speeds in km/h and per-person price bands for shared transport (bus/van/rail) and ferries, in USD per km.
# These are order-of-magnitude bands, NOT a published tariff: typical shared-transport fares seen on operator
# listings such as https://12go.asia and https://www.rome2rio.com. They are converted to the trip currency at
# runtime with frankfurter.app and always labelled indicative. Minimum fare: USD 2 to 4.
ROAD_KMH, FERRY_KMH = 60, 30
ROAD_USD_KM, FERRY_USD_KM = (0.05, 0.11), (0.18, 0.36)
MIN_FARE_USD = (2.0, 4.0)
BAND_CCY = "USD"
ROAD_FACTOR = 1.25  # straight line -> road
# A stop-to-stop hop at or under this road distance is ground, not a flight.
GROUND_MAX_KM = 350


def _table() -> dict:
    try:
        return json.loads(DATA.read_text())["pairs"]
    except Exception:  # noqa: BLE001
        return {}


def is_island(p: dict) -> bool:
    return bool(p.get("island")) or bool(ISLAND.search(p.get("name", "")))


def ids(p: dict) -> set[str]:
    s = {p.get("name", "").lower()} | {a.lower() for a in p.get("aliases", [])}
    if p.get("iata") and p.get("is_airport"):
        s.add(p["iata"].lower())
    return {x for x in s if x}


def road_km(a: dict, b: dict) -> float:
    return km(a["lat"], a["lon"], b["lat"], b["lon"]) * ROAD_FACTOR


def _convert(lo: float, hi: float, src: str, dst: str) -> list[int] | None:
    k = money.rate(src, dst)
    if k is None:
        return None
    return [int(round(x * k, -1)) if x * k >= 50 else int(round(x * k)) for x in (lo, hi)]


def lookup(a: dict, b: dict, currency: str | None = None) -> dict | None:
    """Table entry with `amount` + `currency`, converted to `currency` when given (amount None if FX is down)."""
    t = _table()
    for x in ids(a):
        for y in ids(b):
            e = t.get("|".join(sorted((x, y))))
            if e:
                e = dict(e, source="table")
                if currency and e["currency"].upper() != currency.upper():
                    e["amount"] = _convert(*e["amount"], e["currency"], currency)
                    e["listed_in"] = e["currency"]
                    e["currency"] = currency.upper()
                return e
    return None


def estimate(a: dict, b: dict, currency: str = BAND_CCY) -> dict:
    """{'mode','hours':[lo,hi],'amount':[lo,hi]|None,'currency','km','source'} -- table entry or heuristic,
    in `currency` (amount is None when the FX rate could not be fetched)."""
    e = lookup(a, b, currency)
    d = road_km(a, b)
    if e:
        return dict(e, km=round(d))
    ferry = 0.0
    if is_island(a) or is_island(b):
        ferry = min(max(0.35 * d, 10.0), 80.0) * (2 if is_island(a) and is_island(b) else 1)
        ferry = min(ferry, d)
    road = max(d - ferry, 0.0)
    h = road / ROAD_KMH + ferry / FERRY_KMH + (1.0 if ferry else 0.3)
    lo = max(road * ROAD_USD_KM[0] + ferry * FERRY_USD_KM[0], MIN_FARE_USD[0])
    hi = max(road * ROAD_USD_KM[1] + ferry * FERRY_USD_KM[1], MIN_FARE_USD[1])
    mode = "road + ferry" if ferry and road > 5 else ("ferry" if ferry else "road or rail")
    return {"mode": mode, "hours": [round(h * 0.9, 1), round(h * 1.3, 1)],
            "amount": _convert(lo, hi, BAND_CCY, currency), "currency": currency.upper(), "km": round(d),
            "source": "heuristic"}


def mid(g: dict) -> float:
    return sum(g["amount"]) / 2 if g.get("amount") else 0.0


def needs_ground(a: dict, b: dict) -> bool:
    """True when a stop-to-stop hop should be ground (short, or a known table pair)."""
    return lookup(a, b) is not None or road_km(a, b) <= GROUND_MAX_KM
