"""Free-text destination -> the Wikivoyage article that covers it. Strategy only, no place table.

Tried in order, first existing article wins, every attempt is reported:
1. the text as given;
2. the part before the first comma (drops a trailing ", Country");
3. Wikivoyage opensearch on that part;
4. Nominatim's name for the text, then a Wikivoyage full-text search for it.
"""
from __future__ import annotations

import httpx

from .. import cache
from .common import HEADERS, Result, fail
from .geo import geocode

API = "https://en.wikivoyage.org/w/api.php"


def _exists(title: str) -> str | None:
    """Canonical title when Wikivoyage has a page for `title` (redirects followed), else None."""
    try:
        js = httpx.get(API, params={"action": "query", "titles": title, "redirects": 1, "format": "json",
                                    "formatversion": 2}, headers=HEADERS, timeout=20).json()
    except Exception:  # noqa: BLE001
        return None
    pages = js.get("query", {}).get("pages") or []
    return pages[0]["title"] if pages and not pages[0].get("missing") and not pages[0].get("invalid") else None


def _opensearch(q: str) -> list[str]:
    try:
        js = httpx.get(API, params={"action": "opensearch", "search": q, "limit": 3, "format": "json"},
                       headers=HEADERS, timeout=20).json()
        return list(js[1])
    except Exception:  # noqa: BLE001
        return []


def _search(q: str) -> list[str]:
    try:
        js = httpx.get(API, params={"action": "query", "list": "search", "srsearch": q, "srlimit": 3,
                                    "format": "json", "formatversion": 2}, headers=HEADERS, timeout=20).json()
        return [h["title"] for h in js.get("query", {}).get("search", [])]
    except Exception:  # noqa: BLE001
        return []


def candidates(text: str) -> list[tuple[str, str]]:
    """[(how, title)] in the order they will be tried; later entries are only computed lazily by resolve()."""
    text = text.strip()
    head = text.split(",")[0].strip()
    out = [("as given", text)]
    if head and head != text:
        out.append(("without country", head))
    return out


def resolve(text: str) -> Result:
    """data {title, tried:[...]} for the first Wikivoyage article that exists; ok=False with every attempt listed."""
    def go() -> Result:
        tried: list[str] = []
        url = "https://en.wikivoyage.org/wiki/Special:Search?search=" + text.replace(" ", "+")

        def hit(how: str, title: str) -> Result | None:
            tried.append(title)
            t = _exists(title)
            if t:
                return Result(ok=True, data={"title": t, "how": how, "tried": list(tried)},
                              source_url=f"https://en.wikivoyage.org/wiki/{t.replace(' ', '_')}")
            return None

        for how, title in candidates(text):
            r = hit(how, title)
            if r:
                return r
        head = text.split(",")[0].strip()
        for t in _opensearch(head):
            r = hit("wikivoyage opensearch", t)
            if r:
                return r
        g = geocode(text)
        if g.ok:
            for t in [g.data["name"], *_search(g.data["name"])]:
                r = hit("nominatim name + wikivoyage search", t)
                if r:
                    return r
        return fail(f"no article found for {text!r}; tried " + ", ".join(dict.fromkeys(tried)), url)
    return cache.cached("places:destination", {"q": text, "v": 1}, go)
