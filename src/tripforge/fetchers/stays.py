"""Airbnb search fetcher (entire homes, optionally private rooms for --hostels)."""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from .common import Result, fail

CARDS_JS = """async () => {
  for (let i = 0; i < 4; i++) { window.scrollBy(0, 1200); await new Promise(r => setTimeout(r, 900)); }
  return [...document.querySelectorAll('[itemprop=itemListElement]')].map(c => ({
    t: c.innerText.replace(/\\n+/g, ' | '), u: (c.querySelector('a') || {}).href || ''}));
}"""

_RATING = re.compile(r"([\d.]+) out of 5 average rating,\s*(\d+) reviews?")
_TOTAL = re.compile(r"([₹$€£]|[A-Z]{3})\s?([\d,]+)\s+for\s+(\d+)\s+nights?")
_KIND = re.compile(r"((?:Flat|Apartment|Home|Condo|Townhouse|Villa|Guest house|Guesthouse|Room|Hotel|Hostel|Loft|Bungalow|Cabin|Rental unit|Place)[^|]*? in [^|]+)")
_AFTER = re.compile(r"\|\s*[\d.]+ \(\d+\)\s*\|\s*([^|]+?)\s*\|")


def search_url(slug: str, cin: str, cout: str, adults: int, price_max: int, currency: str,
               room_type: str = "Entire home/apt") -> str:
    host = "airbnb.co.in" if currency == "INR" else "airbnb.com"
    qs = {"checkin": cin, "checkout": cout, "adults": adults, "price_max": price_max, "currency": currency}
    return (f"https://www.{host}/s/{slug}/homes?" + urllib.parse.urlencode(qs) +
            "&room_types%5B%5D=" + urllib.parse.quote(room_type))


def parse_cards(cards: list[dict], nights: int) -> list[dict]:
    out, seen = [], set()
    for c in cards or []:
        t, u = c.get("t", ""), c.get("u", "")
        rm, tm = _RATING.search(t), list(_TOTAL.finditer(t))
        if not (rm and tm and u):
            continue
        total = int(tm[-1].group(2).replace(",", ""))
        n = int(tm[-1].group(3)) or nights
        url = u.split("?")[0]
        if url in seen:
            continue
        seen.add(url)
        km, nm = _KIND.search(t), _AFTER.search(t)
        out.append({
            "name": nm.group(1) if nm else (km.group(1) if km else "Airbnb listing"),
            "kind": km.group(1).strip() if km else "",
            "rating": float(rm.group(1)), "reviews": int(rm.group(2)),
            "total": total, "nights": n, "per_night": round(total / max(n, 1)),
            "badge": "Superhost" if "Superhost" in t else ("Guest favourite" if "Guest favourite" in t else ""),
            "free_cancel": "Free cancellation" in t, "url": url,
        })
    return out


def pick(cands: list[dict], budget_night: int, min_reviews=10, min_rating=4.6):
    good = [c for c in cands if c["reviews"] >= min_reviews and c["rating"] >= min_rating]
    if not good:
        good = [c for c in cands if c["reviews"] >= 3 and c["rating"] >= 4.4]
    for c in good:
        c["score"] = c["rating"] * 10 - 3 * c["per_night"] / max(budget_night, 1)
    good.sort(key=lambda c: -c["score"])
    return good


def fetch_stay(br, slug: str, cin: str, cout: str, nights: int, adults: int, budget_night: int,
               currency: str, evid: Path, tag: str, room_type: str = "Entire home/apt") -> Result:
    url = search_url(slug, cin, cout, adults, budget_night, currency, room_type)
    try:
        br.goto(url, 4500)
        cards = br.eval(CARDS_JS)
    except Exception as e:  # noqa: BLE001
        return fail(f"browser error: {e}", url)
    shot = evid / f"stays_{tag}_{cin}.png"
    has = br.screenshot(shot)
    cands = parse_cards(cards, nights)
    ranked = pick(cands, budget_night)
    r = Result(ok=bool(ranked), data={"ranked": ranked[:6], "n_cards": len(cards or [])}, source_url=url,
               screenshot_path=str(shot) if has else None)
    if not ranked:
        r.error = f"no qualifying listings (cards seen: {len(cards or [])})"
    return r
