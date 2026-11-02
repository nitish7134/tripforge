"""Events in a date window: lunar dates (computed) + festival mentions from Wikivoyage/Wikipedia.

All of it is labelled: lunar dates are astronomical approximations (+/- 1 day), festival rows are
text mentions with a source link, never confirmed listings.
"""
from __future__ import annotations

import datetime as dt
import re

import httpx

from . import cache
from .fetchers.common import HEADERS, Result, fail

SYNODIC = 29.530588853
NEW_MOON_REF = dt.datetime(2000, 1, 6, 18, 14)
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def full_moons(start: dt.date, end: dt.date) -> list[dt.date]:
    out = []
    t0 = NEW_MOON_REF + dt.timedelta(days=SYNODIC / 2)
    n = int(((dt.datetime.combine(start, dt.time()) - t0).days) // SYNODIC) - 1
    while True:
        d = (t0 + dt.timedelta(days=n * SYNODIC)).date()
        if d > end:
            return out
        if d >= start:
            out.append(d)
        n += 1


def _months_in(start: dt.date, end: dt.date) -> list[str]:
    ms, d = [], start.replace(day=1)
    while d <= end:
        ms.append(MONTHS[d.month - 1])
        d = (d + dt.timedelta(days=32)).replace(day=1)
    return ms


def mentions(text: str, start: dt.date, end: dt.date, src: str, url: str, limit: int = 6) -> list[dict]:
    """Sentences in `text` that name a month in the window and look like an event."""
    ms = _months_in(start, end)
    out, seen = [], set()
    plain = re.sub(r"\{\{[^{}]*\}\}|\[\[(?:[^|\]]*\|)?([^\]]*)\]\]|'''?|<[^>]+>", r"\1", text)
    for sent in re.split(r"(?<=[.!?])\s+|\n", plain):
        s = sent.strip(" *#:;")
        if len(s) < 25 or len(s) > 260:
            continue
        if not any(m in s for m in ms):
            continue
        if not re.search(r"festival|celebrat|parade|party|carnival|fair|holiday|new year|christmas|ceremony|race|"
                         r"concert|light|lantern|fireworks|procession", s, re.I):
            continue
        k = s[:60].lower()
        if k in seen:
            continue
        seen.add(k)
        out.append({"text": s, "src": src, "url": url, "tag": "text mention"})
        if len(out) >= limit:
            break
    return out


def wikipedia_festivals(country: str, start: dt.date, end: dt.date) -> Result:
    def go() -> Result:
        url = "https://en.wikipedia.org/w/api.php"
        try:
            js = httpx.get(url, params={"action": "query", "list": "search", "format": "json", "srlimit": 6,
                                        "srsearch": f"festival {country} {' '.join(_months_in(start, end))}"},
                           headers=HEADERS, timeout=20).json()
        except Exception as e:  # noqa: BLE001
            return fail(f"wikipedia error: {type(e).__name__}", url)
        rows = []
        for h in js.get("query", {}).get("search", []):
            snip = re.sub(r"<[^>]+>", "", h.get("snippet", ""))
            rows.append({"text": f"{h['title']}: {snip[:180]}", "src": "wikipedia", "tag": "search hit",
                         "url": "https://en.wikipedia.org/wiki/" + h["title"].replace(" ", "_")})
        return Result(ok=True, data=rows, source_url=url)
    return cache.cached("places:wpfest", {"c": country, "s": str(start), "e": str(end)}, go)


def lunar_rows(start: dt.date, end: dt.date, texts: list[str]) -> list[dict]:
    rows = []
    blob = " ".join(texts).lower()
    for d in full_moons(start, end):
        r = {"text": f"Full moon about {d.strftime('%a %d %b')} (computed, +/- 1 day)", "src": "computed",
             "tag": "est", "date": d.isoformat(), "url": ""}
        if "full moon" in blob:
            r["text"] += "; the destination text mentions full-moon events, check the local date"
        rows.append(r)
    return rows
