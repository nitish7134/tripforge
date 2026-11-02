"""Indicative ground legs (van, bus, rail, ferry) between any two points.

A table entry in data/ground.json wins; otherwise a distance heuristic produces a labelled
"indicative" estimate. Nothing here is a fetched price.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .fetchers.airports import km

DATA = Path(__file__).resolve().parent / "data" / "ground.json"
ISLAND = re.compile(r"\b(koh|ko|isla|ilha|island|isle|nusa|pulau|ile|île|insel|isola)\b", re.I)

# Per-person INR per km for shared transport (bus/van/rail) and ferries; speeds in km/h.
ROAD_KMH, FERRY_KMH = 60, 30
ROAD_INR_KM, FERRY_INR_KM = (4, 9), (15, 30)
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


def lookup(a: dict, b: dict) -> dict | None:
    t = _table()
    for x in ids(a):
        for y in ids(b):
            e = t.get("|".join(sorted((x, y))))
            if e:
                return dict(e, source="table")
    return None


def estimate(a: dict, b: dict) -> dict:
    """{'mode','hours':[lo,hi],'inr':[lo,hi],'km','source'} -- table entry or heuristic."""
    e = lookup(a, b)
    d = road_km(a, b)
    if e:
        return dict(e, km=round(d))
    ferry = 0.0
    if is_island(a) or is_island(b):
        ferry = min(max(0.35 * d, 10.0), 80.0) * (2 if is_island(a) and is_island(b) else 1)
        ferry = min(ferry, d)
    road = max(d - ferry, 0.0)
    h = road / ROAD_KMH + ferry / FERRY_KMH + (1.0 if ferry else 0.3)
    lo = road * ROAD_INR_KM[0] + ferry * FERRY_INR_KM[0]
    hi = road * ROAD_INR_KM[1] + ferry * FERRY_INR_KM[1]
    mode = "road + ferry" if ferry and road > 5 else ("ferry" if ferry else "road or rail")
    return {"mode": mode, "hours": [round(h * 0.9, 1), round(h * 1.3, 1)],
            "inr": [int(round(max(lo, 150), -1)), int(round(max(hi, 300), -1))], "km": round(d),
            "source": "heuristic"}


def needs_ground(a: dict, b: dict) -> bool:
    """True when a stop-to-stop hop should be ground (short, or a known table pair)."""
    return lookup(a, b) is not None or road_km(a, b) <= GROUND_MAX_KM
