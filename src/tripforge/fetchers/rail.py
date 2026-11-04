"""Rail as a first-class ground mode. Strategy only: no routes, stations or fares ship in the repo.

WHAT is fetched and HOW (see docs/FETCH_STRATEGY.md):
- per stop: the destination's Wikivoyage "Get in / By train" text -> stations and typical durations, quoted and dated;
- per leg: a rail-quote ADAPTER chosen by country. An adapter turns (from city, to city, date) into timetable rows
  {train, name, dep, arr, duration_min, classes, fare}. Rows are always tagged "indicative". A fare is only ever
  read from a page; when a source gives none, `fare` is None. When a source blocks or has no data the result is
  ok=False carrying the URL, never an estimate.
- adapters are registered in ADAPTERS by ISO country code. Add one by writing a function with the same signature.
"""
from __future__ import annotations

import re
from typing import Callable

import httpx

from .. import cache
from .common import HEADERS, Result, fail
from .places import section_text, wikivoyage

WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
ERAIL = "https://erail.in/rail/getTrains.aspx?Station_From={a}&Station_To={b}&DataSource=0&Language=0&Cache=true"
NIGHT_START, NIGHT_END = 22 * 60, 5 * 60  # 22:00 - 05:00 counts as a night journey


# ------------------------------------------------------------------ helpers shared by adapters
def is_night(dep_min: int, duration_min: int) -> bool:
    """True when any part of the journey falls between 22:00 and 05:00 local time."""
    for t in range(dep_min, dep_min + max(duration_min, 1), 30):
        m = t % 1440
        if m >= NIGHT_START or m < NIGHT_END:
            return True
    return False


def hm(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _dot_time(s: str) -> int | None:
    m = re.fullmatch(r"(\d{1,2})[.:](\d{2})", (s or "").strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


_CODE = re.compile(r"\|\s*(?:station_)?code\s*=\s*(?:\{\{[^|}]*\|\s*)?([A-Z0-9]{2,5})\b")


def station_code(city: str, cc_hint: str = "") -> Result:
    """Operator station code from the station's Wikipedia infobox (code = ... or {{... code|XX}}).
    Prefers an article whose title starts with the city name. ok=False when no infobox carries a code."""
    def go() -> Result:
        url = WIKIPEDIA
        try:
            hits = httpx.get(WIKIPEDIA, params={"action": "query", "list": "search", "format": "json",
                                                "srsearch": f"{city} railway station code", "srlimit": 6},
                             headers=HEADERS, timeout=20).json()["query"]["search"]
        except Exception as e:  # noqa: BLE001
            return fail(f"wikipedia error: {type(e).__name__}", url)
        titles = [h["title"] for h in hits if h["title"].lower().startswith(city.lower())] or []
        for t in titles:
            try:
                txt = httpx.get(WIKIPEDIA, params={"action": "parse", "page": t, "prop": "wikitext", "format": "json",
                                                   "formatversion": 2, "redirects": 1}, headers=HEADERS,
                                timeout=20).json()["parse"]["wikitext"]
            except Exception:  # noqa: BLE001
                continue
            m = _CODE.search(txt)
            if m:
                return Result(ok=True, data={"code": m.group(1), "station": t},
                              source_url="https://en.wikipedia.org/wiki/" + t.replace(" ", "_"))
        return fail(f"no station code found for {city!r}", url)
    return cache.cached("ground:station", {"c": city, "v": 1}, go)


# ------------------------------------------------------------------ adapter: India (erail.in, keyless page read)
def parse_erail(text: str) -> list[dict]:
    """Rows from erail's getTrains response: records split by '^', fields by '~'.
    Fares are NOT parsed: the page packs them per class without labels, so fare stays None (no guessing)."""
    rows, text = [], (text or "").replace("\n", "").replace("\r", "")
    for rec in text.split("^")[1:]:
        f = rec.split("~")
        if len(f) < 25 or not re.fullmatch(r"\d{4,5}", f[0]):
            continue
        dep, arr, dur = _dot_time(f[10]), _dot_time(f[11]), _dot_time(f[12])
        if dep is None or arr is None or dur is None:
            continue
        classes = re.findall(r"(?:^|\|)([0-9A-Z]{2}):", next((x for x in f if re.match(r"([0-9A-Z]{2}:[^|]*\|)+", x)), ""))
        rows.append({"train": f[0], "name": f[1].strip().title() if f[1].isupper() else f[1].strip(),
                     "from": f[7], "to": f[9], "dep": hm(dep), "arr": hm(arr), "dep_min": dep, "duration_min": dur,
                     "classes": classes, "fare": None})
    return rows


def erail(a: str, b: str, date: str) -> Result:
    """Trains between two cities in India. Station codes come from Wikipedia infobox lookups."""
    ca, cb = station_code(a), station_code(b)
    if not (ca.ok and cb.ok):
        return fail("station code unavailable: " + "; ".join(x.error for x in (ca, cb) if not x.ok),
                    (ca if not ca.ok else cb).source_url)
    url = ERAIL.format(a=ca.data["code"], b=cb.data["code"])

    def go() -> Result:
        try:
            r = httpx.get(url, headers=HEADERS, timeout=25)
        except Exception as e:  # noqa: BLE001
            return fail(f"erail unreachable: {type(e).__name__}", url)
        if r.status_code != 200 or "not found" in r.text[:200].lower() or "<html" in r.text[:200].lower():
            return fail(f"erail returned no timetable (HTTP {r.status_code})", url)
        rows = parse_erail(r.text)
        if not rows:
            return fail("erail lists no direct train for this pair", url)
        for x in rows:
            x["from_station"], x["to_station"] = ca.data["station"], cb.data["station"]
        return Result(ok=True, data=rows, source_url=url)
    return cache.cached("ground:erail", {"u": url, "v": 1}, go)


# country (ISO 3166-1 alpha-2) -> adapter(a_city, b_city, date) -> Result. Others: unavailable with a pointer.
ADAPTERS: dict[str, Callable[[str, str, str], Result]] = {"IN": erail}


def filter_rows(rows: list[dict], max_hours: float | None, night_ok: bool) -> list[dict]:
    out = []
    for r in rows:
        if max_hours is not None and r["duration_min"] > max_hours * 60:
            continue
        if not night_ok and is_night(r["dep_min"], r["duration_min"]):
            continue
        out.append(r)
    return sorted(out, key=lambda r: r["duration_min"])


def quote(a: str, b: str, cc: str, date: str, max_hours: float | None = 18, night_ok: bool = True) -> dict:
    """{'ok', 'rows', 'error', 'url', 'dropped', 'adapter'}. Same-country legs only (an adapter reads one network)."""
    ad = ADAPTERS.get((cc or "").upper())
    if ad is None:
        return {"ok": False, "rows": [], "dropped": 0, "adapter": None, "url": "",
                "error": f"no rail-quote adapter for country {cc or '?'} (see docs/FETCH_STRATEGY.md to add one)"}
    r = ad(a, b, date)
    if not r.ok:
        return {"ok": False, "rows": [], "dropped": 0, "adapter": ad.__name__, "url": r.source_url, "error": r.error}
    rows = filter_rows(r.data, max_hours, night_ok)
    return {"ok": bool(rows), "rows": rows[:5], "dropped": len(r.data) - len(rows), "adapter": ad.__name__,
            "url": r.source_url, "fetched_at": r.fetched_at,
            "error": None if rows else ("every train breaks the brief's night-travel or max-hours limit"
                                         if r.data else "no trains")}


# ------------------------------------------------------------------ Wikivoyage "By train"
def _plain(t: str) -> str:
    t = re.sub(r"\[\[(?:File|Image):[^\n]*?\]\]\s*", "", t, flags=re.I)
    t = re.sub(r"\{\{[^{}]*\}\}|<[^>]+>|'{2,3}", "", t)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def by_train_note(stop_name: str, limit: int = 420) -> dict | None:
    """Quoted 'By train' paragraph of the stop's Wikivoyage 'Get in' section (stations, typical durations)."""
    w = wikivoyage(stop_name)
    if not w.ok:
        return None
    body = section_text(w.data.get("text", ""), "By train")
    txt = _plain(body)
    if len(txt) < 20:
        return None
    return {"text": txt[:limit].rsplit(" ", 1)[0] + ("..." if len(txt) > limit else ""), "url": w.source_url,
            "tag": "community text, check the operator"}
