"""Resolve any place name into a stop: coordinates, country, access airports.

Curated entries in data/places.json (optional examples) add stay areas, highlights and a stay
centre; everything else comes from Nominatim + OurAirports, so any destination works.
"""
from __future__ import annotations

import re

from .fetchers import airports as AP
from .fetchers.geo import geocode
from .fetchers.misc import load

# A stop whose nearest airport is further than this needs a ground transfer from the airport.
OWN_AIRPORT_KM = 40  # big-city airports sit 20-40 km out


class StopError(ValueError):
    pass


def _curated(name: str) -> dict | None:
    cities = load("places.json")["cities"]
    k = name.strip().lower()
    if k in cities:
        return dict(cities[k])
    for c in cities.values():
        if k in [a.lower() for a in c.get("aliases", [])]:
            return dict(c)
    return None


def resolve(name: str, country_hint: str = "", iata: str | None = None) -> dict:
    """-> {name, lat, lon, cc, country, airport, airport_km, alt_airports, areas, highlights, ...}."""
    cur = _curated(name)
    if cur:
        s = cur
        if not s.get("country"):
            s["country"] = AP.countries().get(s["cc"], s["cc"])
    else:
        g = geocode(f"{name}, {country_hint}" if country_hint else name)
        if not g.ok:
            raise StopError(f"cannot find {name!r}: {g.error}")
        d = g.data
        s = {"name": name.strip().title() if name.islower() else name.strip(), "lat": d["lat"], "lon": d["lon"],
             "cc": d["cc"], "country": d["country"] or AP.countries().get(d["cc"], d["cc"]),
             "island": d.get("type") == "island", "bbox": d["bbox"], "areas": [], "highlights": [],
             "airbnb": f"{name.strip().replace(' ', '-')}--{(d['country'] or '').replace(' ', '-')}"}
    near = AP.nearest(s["lat"], s["lon"], k=4)
    if iata:
        s["iata"] = iata.upper()
    primary = AP.by_iata(s["iata"]) if s.get("iata") else (near[0] if near else None)
    if not primary:
        raise StopError(f"no scheduled-service airport within 400 km of {name}")
    pkm = round(AP.km(s["lat"], s["lon"], primary["lat"], primary["lon"]))
    s.update(iata=primary["iata"], airport=primary["name"], airport_city=primary["city"] or primary["name"],
             airport_km=pkm, airport_lat=primary["lat"], airport_lon=primary["lon"])
    # Alternatives are only worth pricing when the stop has no airport of its own.
    s["alt_airports"] = [] if pkm <= OWN_AIRPORT_KM else [
        {"iata": a["iata"], "name": a["name"], "city": a["city"], "km": a["km"], "lat": a["lat"], "lon": a["lon"]}
        for a in near if a["iata"] != primary["iata"] and a["km"] <= 200][:2]
    s.setdefault("areas", [])
    s.setdefault("highlights", [])
    return s


def airport_point(a: dict) -> dict:
    """An airport as a ground endpoint."""
    return {"name": a.get("city") or a.get("name"), "iata": a["iata"], "is_airport": True,
            "lat": a["lat"], "lon": a["lon"], "aliases": [a.get("name", "")]}


def parse_spec(spec: str, country_hint: str = "") -> list[dict]:
    """'CityA:4,Island B:4@XYZ,CityC:2' -> resolved stops with nights."""
    out = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        m = re.match(r"^(?P<name>[^:@]+?)\s*(?::\s*(?P<n>\d+))?\s*(?:@(?P<iata>[A-Za-z]{3}))?$", part)
        if not m:
            raise StopError(f"cannot parse stop {part!r}; use Name:nights[@IATA]")
        s = resolve(m["name"], country_hint, m["iata"])
        s["nights"] = int(m["n"] or 2)
        out.append(s)
    if not out:
        raise StopError("no stops given")
    return out
