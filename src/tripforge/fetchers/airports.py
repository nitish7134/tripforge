"""Nearest commercial airport for any point on Earth, from OurAirports' public-domain CSVs.

https://ourairports.com/data/ (keyless). Downloaded once into <repo>/cache/ and refreshed every 30 days.
Only airports with scheduled service and an IATA code are considered.
"""
from __future__ import annotations

import csv
import functools
import math
import time
from pathlib import Path

import httpx

from .. import cache
from .common import HEADERS

BASE = "https://davidmegginson.github.io/ourairports-data/"
MAX_AGE = 30 * 24 * 3600


def _file(name: str) -> Path:
    p = cache.repo_root() / "cache" / name
    if not p.exists() or time.time() - p.stat().st_mtime > MAX_AGE:
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = httpx.get(BASE + name, headers=HEADERS, timeout=90, follow_redirects=True)
            r.raise_for_status()
            tmp = p.with_suffix(".part")
            tmp.write_bytes(r.content)
            tmp.replace(p)
        except Exception:  # noqa: BLE001
            if not p.exists():
                raise
    return p


@functools.lru_cache(maxsize=1)
def airports() -> list[dict]:
    out = []
    with _file("airports.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["scheduled_service"] != "yes" or not r["iata_code"] or r["type"] not in (
                    "large_airport", "medium_airport", "small_airport"):
                continue
            out.append({"iata": r["iata_code"], "name": r["name"], "city": r["municipality"],
                        "cc": r["iso_country"], "lat": float(r["latitude_deg"]), "lon": float(r["longitude_deg"]),
                        "size": {"large_airport": 3, "medium_airport": 2}.get(r["type"], 1)})
    return out


@functools.lru_cache(maxsize=1)
def countries() -> dict[str, str]:
    with _file("countries.csv").open(newline="", encoding="utf-8") as f:
        return {r["code"]: r["name"] for r in csv.DictReader(f)}


def by_iata(code: str) -> dict | None:
    code = code.upper()
    hits = [a for a in airports() if a["iata"] == code]
    return max(hits, key=lambda a: a["size"]) if hits else None


def km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def nearest(lat: float, lon: float, k: int = 3, min_size: int = 1) -> list[dict]:
    """k nearest scheduled-service airports, each with `km`. A small airport only wins over a
    medium/large one when it is much closer (small strips often have one daily flight)."""
    rows = []
    for a in airports():
        if a["size"] < min_size:
            continue
        d = km(lat, lon, a["lat"], a["lon"])
        if d < 400:
            rows.append(dict(a, km=round(d)))
    rows.sort(key=lambda a: a["km"] * (1.0 if a["size"] >= 2 else 1.8))
    return rows[:k]
