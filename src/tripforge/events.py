"""Events in a date window: public holidays (Nager.Date), festival mentions from Wikivoyage/Wikipedia, and
moon-dated events only when a stop's guide article mentions one.

All of it is labelled: holidays are fetched, lunar dates are astronomical approximations (+/- 1 day),
festival rows are text mentions with a source link, never confirmed listings.
"""
from __future__ import annotations

import datetime as dt
import re

import httpx

from . import cache
from .fetchers.common import HEADERS, Result, fail
from .fetchers.places import flatten_templates, section_text

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


_UNIT = re.compile(r"([^()]+?)\(([^()]*?(?:%s)[^()]*?)\)" % "|".join(m[:3] for m in MONTHS))


def split_snippet(snip: str, src: str, url: str) -> list[dict]:
    """Break a glued 'Name, Place (Month) Name, Place (Month-Month) ...' text into one event per unit.
    Only the structure `Name[, Place] (month...)` is read; nothing about any event is known in advance."""
    out = []
    for name, when in _UNIT.findall(re.sub(r"\s+", " ", snip)):
        name = name.strip(" ,;:.-\u2013\u2014*")
        name = re.sub(r"^.*?(?:\.\.\.|\bincluding\b|\bsuch as\b|:)\s*", "", name).strip(" ,;")
        if not 3 <= len(name) <= 90:
            continue
        head, _, place = name.rpartition(",")
        label = f"{head.strip()} in {place.strip()}" if head and place.strip() else name
        out.append({"text": f"{label} ({when.strip()})", "src": src, "url": url,
                    "tag": "text mention, approximate month", "when": when.strip()})
    return out


def in_window(when: str, start: dt.date, end: dt.date) -> bool:
    return any(m[:3].lower() in when.lower() for m in _months_in(start, end))


def section_mentions(text: str, start: dt.date, end: dt.date, src: str, url: str, limit: int = 6) -> list[dict]:
    """Bullets of a guide article's Events / Festivals / Holidays section that name a month in the window."""
    body = section_text(flatten_templates(text), "Festivals and events", "Events", "Festivals", "Holidays",
                        "Festivals and holidays")
    ms = _months_in(start, end)
    out, seen = [], set()
    for ln in body.splitlines():
        if not ln.lstrip().startswith(("*", "#", ";", ":")):
            continue
        plain = re.sub(r"\{\{[^{}]*\}\}|<[^>]+>|'{2,3}", "", re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", ln))
        plain = plain.strip(" *#:;")
        if len(plain) < 12 or not any(m in plain for m in ms):
            continue
        k = plain[:50].lower()
        if k in seen:
            continue
        seen.add(k)
        out.append({"text": plain[:240], "src": src, "url": url, "tag": "guide section, community text"})
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
            snip = re.sub(r"<[^>]+>", "", h.get("snippet", "")).replace("&#039;", "'").replace("&quot;", '"')
            if h["title"] in MONTHS or not any(m in snip or m in h["title"] for m in _months_in(start, end)):
                continue
            page = "https://en.wikipedia.org/wiki/" + h["title"].replace(" ", "_")
            units = [u for u in split_snippet(snip, "wikipedia", page) if in_window(u["when"], start, end)]
            rows += units or [{"text": f"{h['title']}: {snip[:180]}", "src": "wikipedia", "tag": "search hit",
                               "url": page}]
        return Result(ok=True, data=rows, source_url=url)
    return cache.cached("places:wpfest", {"c": country, "s": str(start), "e": str(end), "v": 3}, go)


NAGER = "https://date.nager.at/api/v3/PublicHolidays/{year}/{cc}"


def public_holidays(cc: str, start: dt.date, end: dt.date) -> Result:
    """Public holidays of country `cc` inside [start, end]: data = [{date, name, local}]."""
    def go() -> Result:
        rows, url = [], NAGER.format(year=start.year, cc=cc.upper())
        try:
            for y in range(start.year, end.year + 1):
                url = NAGER.format(year=y, cc=cc.upper())
                r = httpx.get(url, headers=HEADERS, timeout=20)
                if r.status_code != 200:
                    return fail(f"nager.date HTTP {r.status_code} for {cc}", url)
                rows += [{"date": h["date"], "name": h["name"], "local": h.get("localName", "")} for h in r.json()
                         if start.isoformat() <= h["date"] <= end.isoformat()]
        except Exception as e:  # noqa: BLE001
            return fail(f"nager.date error: {type(e).__name__}", url)
        return Result(ok=True, data=rows, source_url=url)
    return cache.cached("holidays", {"cc": cc.upper(), "s": str(start), "e": str(end)}, go)


def holiday_rows(res: Result, label: str, role: str) -> list[dict]:
    """role: 'home' (leave-day planning) or 'destination' (closures, crowds)."""
    if not res.ok:
        return []
    why = {"home": "plan leave days around it",
           "both": "plan leave days around it and expect closures and crowds"}.get(role, "expect closures and crowds")
    return [{"text": f"Public holiday in {label}: {h['name']} on {dt.date.fromisoformat(h['date']).strftime('%a %d %b')} ({why})",
             "src": "nager.date", "tag": "live", "date": h["date"], "url": res.source_url} for h in res.data]


_MOON = re.compile(r"\b(full|new) moon\b", re.I)


def lunar_rows(start: dt.date, end: dt.date, texts: list[str]) -> list[dict]:
    """Moon-dated rows only when a stop's guide text mentions a moon-dated event; never by default."""
    blob = " ".join(texts)
    m = _MOON.search(blob)
    if not m:
        return []
    phase = m.group(1).lower()
    dates = full_moons(start, end) if phase == "full" else []
    return [{"text": f"{phase.capitalize()} moon about {d.strftime('%a %d %b')} (computed, +/- 1 day); the destination "
                     "guide mentions moon-dated events, check the local date", "src": "computed", "tag": "est",
             "date": d.isoformat(), "url": ""} for d in dates]
