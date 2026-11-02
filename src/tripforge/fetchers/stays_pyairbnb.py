"""Browserless Airbnb search via pyairbnb (https://github.com/johnbalvin/pyairbnb).

Fragile by nature: Airbnb rotates its persisted-query hash and API contract. Any exception, 403 or
empty page returns ok=False so the caller can fall back to the Playwright fetcher.
"""
from __future__ import annotations

import re

from .common import Result, fail
from .stays import search_url

_N = re.compile(r"(\d+)\s+night")


def to_rows(raw: list[dict], nights: int, cin: str, cout: str, adults: int, currency: str) -> list[dict]:
    host = "airbnb.com"  # the currency= parameter selects the display currency
    out = []
    for x in raw or []:
        unit = (x.get("price") or {}).get("unit") or {}
        amt = unit.get("discount") or unit.get("amount")
        if not amt:
            continue
        q = unit.get("qualifier") or ""
        m = _N.search(q)
        total = float(amt) if m else float(amt) * nights  # "for 4 nights" is a total; "night" is per night
        n = int(m.group(1)) if m else nights
        rt = x.get("rating") or {}
        try:
            rating, reviews = float(rt.get("value") or 0), int(rt.get("reviewCount") or 0)
        except (TypeError, ValueError):
            rating, reviews = 0.0, 0
        title = x.get("title") or ""
        kind, _, area = title.partition(" in ")
        badges = x.get("badges") or []
        out.append({
            "name": (x.get("name") or title or "Airbnb listing").strip(), "kind": title, "room_type": kind.strip(),
            "area": area.strip(), "rating": rating, "reviews": reviews, "total": round(total), "nights": n,
            "per_night": round(total / max(n, 1)),
            "badge": "Guest favourite" if any("GUEST_FAVORITE" in str(b).upper() for b in badges)
                     else ("Superhost" if any("SUPERHOST" in str(b).upper() for b in badges) else ""),
            "free_cancel": False,
            "url": f"https://www.{host}/rooms/{x['room_id']}?check_in={cin}&check_out={cout}&adults={adults}",
        })
    return out


def pick(rows: list[dict], min_reviews=10, min_rating=4.6) -> list[dict]:
    good = [r for r in rows if r["reviews"] >= min_reviews and r["rating"] >= min_rating]
    seen, out = set(), []
    for r in sorted(good, key=lambda r: r["total"]):
        if r["url"] not in seen:
            seen.add(r["url"])
            out.append(r)
    return out


def fetch_stay(bbox: tuple, slug: str, cin: str, cout: str, nights: int, adults: int, budget_night: int,
               currency: str, room_type: str = "Entire home/apt", max_pages: int = 3) -> Result:
    url = search_url(slug, cin, cout, adults, budget_night, currency, room_type)
    try:
        import pyairbnb
    except Exception as e:  # noqa: BLE001
        return fail(f"pyairbnb not installed: {e}", url)
    ne_lat, ne_lon, sw_lat, sw_lon = bbox
    raw: list = []
    try:
        from pyairbnb import api, search, standardize, utils
        key = api.get("")
        cursor = ""
        for _page in range(max_pages):
            res = search.get(key, cursor, cin, cout, ne_lat, ne_lon, sw_lat, sw_lon, 13, currency, room_type, 0,
                             int(budget_night), [], False, adults, 0, 0, 0, 0, 0, "en", "", "")
            raw += standardize.from_search(res)
            cursor = (utils.get_nested_value(res, "data.presentation.staysSearch.results.paginationInfo", {}) or {}
                      ).get("nextPageCursor")
            if not cursor or len(pick(to_rows(raw, nights, cin, cout, adults, currency))) >= 4:
                break
    except Exception as e:  # noqa: BLE001
        return fail(f"pyairbnb error: {type(e).__name__}: {str(e)[:160]}", url)
    rows = to_rows(raw, nights, cin, cout, adults, currency)
    ranked = pick(rows)
    r = Result(ok=bool(ranked), data={"ranked": ranked[:6], "n_cards": len(raw), "backend": "pyairbnb"},
               source_url=url)
    if not ranked:
        r.error = f"pyairbnb: no listing with >=10 reviews and >=4.6 (seen {len(raw)})"
    return r
