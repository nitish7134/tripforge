"""Nominatim geocoding (keyless, 1 req/s, User-Agent required), cached 30 days."""
from __future__ import annotations

import threading
import time

from .. import cache
from .common import Result, client, fail

NOMINATIM = "https://nominatim.openstreetmap.org/search"
_lock = threading.Lock()
_last = [0.0]


def _polite():
    with _lock:
        wait = 1.05 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def geocode(q: str) -> Result:
    """-> data {lat, lon, bbox:[s, n, w, e], name}."""
    def go() -> Result:
        _polite()
        url = f"{NOMINATIM}?q={q}&format=json&limit=1&accept-language=en"
        try:
            with client(20) as c:
                js = c.get(NOMINATIM, params={"q": q, "format": "json", "limit": 1, "accept-language": "en",
                                              "addressdetails": 1}).json()
        except Exception as e:  # noqa: BLE001
            return fail(f"nominatim error: {e}", url)
        if not js:
            return fail(f"nominatim: no match for {q!r}", url)
        h = js[0]
        bb = [float(x) for x in h["boundingbox"]]
        ad = h.get("address") or {}
        return Result(ok=True, data={"lat": float(h["lat"]), "lon": float(h["lon"]), "bbox": bb,
                                     "name": h.get("name") or q, "display": h.get("display_name", q),
                                     "cc": (ad.get("country_code") or "").upper(), "country": ad.get("country", ""),
                                     "type": h.get("type", ""), "class": h.get("class", "")}, source_url=url)
    return cache.cached("geo", {"q": q, "v": 2}, go)


def stay_bbox(city: str, country: str, area: str | None, lat: float, lon: float,
              center: list | None = None) -> tuple[float, float, float, float]:
    """(ne_lat, ne_lon, sw_lat, sw_lon). A `center` derived from the Wikivoyage Sleep listings wins; small places
    use their own Nominatim bbox; big cities are narrowed to ~4 km around the preferred area."""
    d = 0.035
    if center:
        return center[0] + d, center[1] + d, center[0] - d, center[1] - d
    g = geocode(f"{city}, {country}")
    if g.ok:
        s, n, w, e = g.data["bbox"]
        if (n - s) < 0.2 and (e - w) < 0.2:
            return n, e, s, w
        lat, lon = g.data["lat"], g.data["lon"]
    if area:
        a = geocode(f"{area}, {city}, {country}")
        if a.ok:
            lat, lon = a.data["lat"], a.data["lon"]
    return lat + d, lon + d, lat - d, lon - d
