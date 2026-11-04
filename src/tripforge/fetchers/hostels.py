"""Hostel beds and private rooms from Hostelworld's public property endpoints (keyless).

A property is identified by the numeric id in its Hostelworld URL (`.../hostels/p/<id>/...`). The brief lists the
ids per stop (see TRIPS.md `stays.hostelworld`); nothing is hardcoded here. Two calls per property:
`/properties/<id>/` for name, rating and review count, `/properties/<id>/availability/` for live per-night and
total prices by room. Any HTTP error or empty payload returns ok=False with the URL so the row reads unavailable.
"""
from __future__ import annotations

from .. import cache
from .common import Result, client, fail

API = "https://prod.apigee.hostelworld.com/legacy-hwapi-service/2.2/properties"


def property_url(pid: int | str) -> str:
    return f"https://www.hostelworld.com/st/hostels/p/{pid}/"


def parse_rooms(av: dict) -> dict:
    """availability payload -> {dorms: [...], privates: [...]} sorted by per-night price (cheapest rate plan)."""
    out = {"dorms": [], "privates": []}
    for kind in out:
        for r in ((av.get("rooms") or {}).get(kind) or []):
            lp = (r.get("lowestPricePerNight") or {}).get("value")
            totals = [float(t["price"]["value"]) for t in r.get("totalPrice") or [] if t.get("price", {}).get("value")]
            if not lp:
                continue
            out[kind].append({
                "room": r.get("name", ""), "per_night": round(float(lp)), "total": round(min(totals)) if totals else None,
                "available": r.get("totalBedsAvailable") if kind == "dorms" else r.get("totalRoomsAvailable"),
                "ensuite": str(r.get("ensuite", "0")) == "1",
            })
        out[kind].sort(key=lambda x: x["per_night"])
    return out


def parse_property(p: dict) -> dict:
    rt = p.get("rating") or {}
    return {"id": str(p.get("id", "")), "name": p.get("name") or p.get("transName") or f"Hostelworld #{p.get('id')}",
            "type": p.get("type", "HOSTEL"), "rating": round(float(rt.get("overall") or 0) / 10, 1),  # 98 -> 9.8
            "reviews": int(p.get("totalRatings") or 0), "checkin": p.get("checkIn") or {},
            "deposit_pct": p.get("depositPercentage")}


def fetch_hostel(pid: int | str, cin: str, nights: int, guests: int, currency: str) -> Result:
    """One Hostelworld property for the dates: {name, rating (/10), reviews, dorms, privates, url}."""
    params = {"pid": str(pid), "cin": cin, "n": nights, "g": guests, "ccy": currency, "v": 1}

    def go() -> Result:
        url = property_url(pid)
        try:
            with client(25) as c:
                prop = c.get(f"{API}/{pid}/", params={"currency": currency}).json()
                av = c.get(f"{API}/{pid}/availability/", params={"date-start": cin, "num-nights": nights,
                                                                 "guests": guests, "currency": currency}).json()
        except Exception as e:  # noqa: BLE001
            return fail(f"hostelworld error: {type(e).__name__}: {str(e)[:120]}", url)
        if not isinstance(prop, dict) or not prop.get("id"):
            return fail("hostelworld: property not found", url)
        d = parse_property(prop)
        d.update(parse_rooms(av if isinstance(av, dict) else {}), url=url, nights=nights, guests=guests,
                 currency=currency, deposit_pct=(av or {}).get("depositPercentage", d.get("deposit_pct")))
        if not d["dorms"] and not d["privates"]:
            r = Result(ok=False, data=d, source_url=url)
            r.error = "hostelworld: no availability for these dates"
            return r
        return Result(ok=True, data=d, source_url=url)

    return cache.cached("hostels", params, go)


def pick(results: list[Result]) -> list[dict]:
    """Across a stop's hostels, cheapest dorm bed first; each entry carries both dorm and private options."""
    good = [r.data for r in results if r.ok and r.data]
    return sorted(good, key=lambda d: (d["dorms"][0]["per_night"] if d["dorms"]
                                       else d["privates"][0]["per_night"] if d["privates"] else 1e12))
