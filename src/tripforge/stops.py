"""Resolve any place name into a stop: coordinates, country, access airports.

Coordinates and country come from Nominatim, airports from OurAirports, and stay districts, highlights and
a stay centre from the stop's Wikivoyage article (Districts, Sleep, See, Do). No curated data ships in the repo.
"""
from __future__ import annotations

import re

from .fetchers import airports as AP
from .fetchers.geo import PIN_DEG, geocode, geocode_point
from .fetchers.places import guide

# A stop whose nearest airport is further than this needs a ground transfer from the airport.
OWN_AIRPORT_KM = 40  # big-city airports sit 20-40 km out


class StopError(ValueError):
    pass


def resolve(name: str, country_hint: str = "", iata: str | None = None, area: str | None = None) -> dict:
    """-> {name, lat, lon, cc, country, airport, airport_km, alt_airports, areas, highlights, ...}.
    `area` pins the stay search to a named district/beach inside the stop (walking-distance radius)."""
    g = geocode(f"{name}, {country_hint}" if country_hint else name)
    if not g.ok:
        raise StopError(f"cannot find {name!r}: {g.error}")
    d = g.data
    s = {"name": name.strip().title() if name.islower() else name.strip(), "lat": d["lat"], "lon": d["lon"],
         "cc": d["cc"], "country": d["country"] or AP.countries().get(d["cc"], d["cc"]),
         "island": d.get("type") == "island", "bbox": d["bbox"],
         "airbnb": f"{name.strip().replace(' ', '-')}--{(d['country'] or '').replace(' ', '-')}"}
    gd = guide(s["name"])
    s.update(guide_found=gd["found"], guide_url=gd.get("url"), areas=gd.get("areas", []),
             highlights=gd.get("highlights", []), stay_center=gd.get("stay_center"), stay_area=None, stay_radius=None)
    s["lat"], s["lon"] = town_point(d.get("class", ""), s["lat"], s["lon"], gd.get("stay_center"))
    if area:
        a = geocode_point(f"{area}, {s['name']}, {s['country']}")
        if not a.ok:
            raise StopError(f"cannot find stay area {area!r} in {s['name']}: {a.error}")
        s.update(stay_area=area.strip(), stay_center=[a.data["lat"], a.data["lon"]], stay_radius=PIN_DEG)
    near = AP.nearest(s["lat"], s["lon"], k=4)
    if iata:
        s["iata"] = iata.upper()
    primary = AP.by_iata(s["iata"]) if s.get("iata") else (near[0] if near else None)
    if not primary:
        raise StopError(f"no scheduled-service airport within 400 km of {name}")
    pkm = round(AP.km(s["lat"], s["lon"], primary["lat"], primary["lon"]))
    s.update(iata=primary["iata"], airport=primary["name"], airport_city=primary["city"] or primary["name"],
             airport_km=pkm, airport_lat=primary["lat"], airport_lon=primary["lon"])
    s["alt_airports"] = alt_airports(primary, pkm, near)
    return s


# An administrative boundary's centroid can sit in the sea or the hills (tens of km from the nearest road),
# which turns every road leg into a "ferry". Where the guide's Sleep listings cluster is the town.
CENTROID_MAX_KM = 40


def town_point(hit_class: str, lat: float, lon: float, center: list | None) -> tuple[float, float]:
    """The point to route and search from: the Wikivoyage listings centre when the geocode is an area, else the hit."""
    if hit_class == "boundary" and center and AP.km(lat, lon, center[0], center[1]) <= CENTROID_MAX_KM:
        return float(center[0]), float(center[1])
    return lat, lon


# A city often has two airports close together (a downtown strip and the international hub) and OurAirports sizes
# them alike, so no rule can guess which one the long-haul flights use: every airport this close is priced and
# the cheapest flight-plus-transfer wins.
TWIN_KM = 50


def alt_airports(primary: dict, pkm: int, near: list[dict]) -> list[dict]:
    """Other airports worth pricing: all within TWIN_KM, and up to 200 km when the stop has no airport of its own."""
    far_ok = pkm > OWN_AIRPORT_KM
    return [{"iata": a["iata"], "name": a["name"], "city": a["city"], "km": a["km"], "lat": a["lat"], "lon": a["lon"]}
            for a in near if a["iata"] != primary["iata"] and (a["km"] <= TWIN_KM or (far_ok and a["km"] <= 200))][:2]


def airport_point(a: dict) -> dict:
    """An airport as a ground endpoint."""
    return {"name": a.get("city") or a.get("name"), "iata": a["iata"], "is_airport": True,
            "lat": a["lat"], "lon": a["lon"], "aliases": [a.get("name", "")]}


SPEC = re.compile(r"^(?P<name>[^:@/]+?)\s*(?:/\s*(?P<area>[^:@]+?))?\s*(?::\s*(?P<n>\d+))?\s*(?:@\s*(?P<iata>[A-Za-z]{3}))?$")


def split_spec(spec: str) -> list[dict]:
    """'CityA:4,City B/Beach Area:2@XYZ' -> [{name, area, nights, iata}] without any network call."""
    out = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        m = SPEC.match(part)
        if not m:
            raise StopError(f"cannot parse stop {part!r}; use Name[/Stay area]:nights[@IATA]")
        out.append({"name": m["name"].strip(), "area": (m["area"] or "").strip() or None,
                    "nights": int(m["n"] or 2), "iata": m["iata"]})
    if not out:
        raise StopError("no stops given")
    return out


def parse_spec(spec: str, country_hint: str = "") -> list[dict]:
    """'CityA:4,Island B:4@XYZ,CityC/District:2' -> resolved stops with nights."""
    out = []
    for p in split_spec(spec):
        s = resolve(p["name"], country_hint, p["iata"], p["area"])
        s["nights"] = p["nights"]
        out.append(s)
    if not out:
        raise StopError("no stops given")
    return out
