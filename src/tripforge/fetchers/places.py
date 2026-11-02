"""Real named places per stop: OpenStreetMap Overpass (diet-tagged food, nightlife, sights) + Wikivoyage See/Do/Eat.

Keyless. Overpass is called at most once a second with a User-Agent; everything is cached 7 days.
OSM tags are sparse on small islands, so callers keep the curated highlight list as a fallback.
"""
from __future__ import annotations

import re
import threading
import time

from .. import cache
from .common import HEADERS, Result, fail

import httpx

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
WIKIVOYAGE = "https://en.wikivoyage.org/w/api.php"
_lock = threading.Lock()
_last = [0.0]


def _polite():
    with _lock:
        wait = 1.05 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


# Generic dietary tags a brief may list in `prefs`: pref -> (OSM diet:* key, regex for Wikivoyage Eat listings).
# No cuisine is assumed; a diet is only searched when the traveller asks for it.
DIETS = {"veg": ("diet:vegetarian", r"vegetarian|vegan|\bveg\b"), "vegan": ("diet:vegan", r"vegan"),
         "halal": ("diet:halal", r"halal"), "kosher": ("diet:kosher", r"kosher"),
         "gluten-free": ("diet:gluten_free", r"gluten")}


def diets_in(prefs) -> tuple[str, ...]:
    return tuple(sorted(p for p in (prefs or []) if p in DIETS))


def _q(lat: float, lon: float, r: int, diets: tuple = ()) -> str:
    a = f"(around:{r},{lat},{lon})"
    parts = [f'node["amenity"="{x}"]["{DIETS[d][0]}"]{a};' for d in diets for x in ("restaurant", "cafe", "fast_food")]
    parts += [f'node["amenity"="{x}"]["name"]{a};' for x in ("bar", "nightclub", "pub")]
    parts += [f'nwr["tourism"="{x}"]["name"]{a};' for x in ("attraction",)]
    parts += [f'way["natural"="beach"]["name"]{a};']
    return "[out:json][timeout:60];(" + "".join(parts) + ");out center tags 200;"


def _name(t: dict) -> str | None:
    n = t.get("name:en") or t.get("name")
    if not n or not re.search(r"[A-Za-z]", n):
        return None
    return n.strip()


def classify(elements: list[dict], diets: tuple = ()) -> dict:
    out = {"diet": {d: [] for d in diets}, "nightlife": [], "sights": []}
    seen = set()
    for e in elements:
        t = e.get("tags") or {}
        n = _name(t)
        if not n or n.lower() in seen:
            continue
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        item = {"name": n, "lat": lat, "lon": lon,
                "osm": f"https://www.openstreetmap.org/{e.get('type', 'node')}/{e.get('id')}"}
        am = t.get("amenity", "")
        hit = [d for d in diets if t.get(DIETS[d][0]) in ("yes", "only")]
        if am in ("restaurant", "cafe", "fast_food") and hit:
            for d in hit:
                out["diet"][d].append(dict(item, kind=f"only {d}" if t.get(DIETS[d][0]) == "only" else f"{d} options"))
        elif am in ("bar", "nightclub", "pub"):
            item["kind"] = am
            out["nightlife"].append(item)
        elif t.get("tourism") in ("attraction", "viewpoint") or t.get("natural") == "beach":
            item["kind"] = t.get("tourism") or "beach"
            out["sights"].append(item)
        else:
            continue
        seen.add(n.lower())
    # Nightclubs before bars; pure-veg before veg-options; named attractions before viewpoints.
    out["nightlife"].sort(key=lambda x: {"nightclub": 0, "bar": 1, "pub": 2}.get(x["kind"], 3))
    for lst in out["diet"].values():
        lst.sort(key=lambda x: not x["kind"].startswith("only"))
    out["sights"].sort(key=lambda x: {"attraction": 0, "beach": 1, "viewpoint": 2}.get(x["kind"], 3))
    return out


def overpass(lat: float, lon: float, radius: int = 5000, diets: tuple = ()) -> Result:
    params = {"lat": round(lat, 3), "lon": round(lon, 3), "r": radius, "d": list(diets), "v": 3}

    def go() -> Result:
        q, err, t0 = _q(lat, lon, radius, diets), "overpass unavailable", time.time()
        # The public instance is often slow (30-60 s) or briefly 429/502; retry within a 100 s budget.
        for ep in (OVERPASS[0],):  # degraded public instance: one bounded try, Wikivoyage fills the gap
            if time.time() - t0 > 100:
                break
            _polite()
            try:
                r = httpx.post(ep, data={"data": q}, headers=HEADERS, timeout=httpx.Timeout(40, connect=8))
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    return Result(ok=True, data=classify(r.json().get("elements", []), diets), source_url=ep)
                err = f"overpass HTTP {r.status_code}"
                time.sleep(4)
            except Exception as e:  # noqa: BLE001
                err = f"overpass error: {type(e).__name__}"
        return fail(err, OVERPASS[0])
    return cache.cached("places:overpass", params, go)


_LISTING = re.compile(r"\{\{\s*(see|do|eat|drink|sleep|listing)\s*\|(.*?)\}\}", re.S | re.I)


def _field(body: str, k: str) -> str:
    m = re.search(rf"\|\s*{k}\s*=\s*([^|]*)", "|" + body)
    return re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", m.group(1)).strip() if m else ""


def wikivoyage(page: str) -> Result:
    """See/Do listings (name + first sentence) and the lead text from a Wikivoyage article."""
    def go() -> Result:
        url = f"https://en.wikivoyage.org/wiki/{page.replace(' ', '_')}"
        try:
            js = httpx.get(WIKIVOYAGE, params={"action": "parse", "page": page, "prop": "wikitext", "format": "json",
                                               "formatversion": 2, "redirects": 1}, headers=HEADERS, timeout=25).json()
            text = js["parse"]["wikitext"]
            url = f"https://en.wikivoyage.org/wiki/{js['parse']['title'].replace(' ', '_')}"
        except Exception as e:  # noqa: BLE001
            return fail(f"wikivoyage error: {type(e).__name__}", url)
        items = []
        for kind, body in _LISTING.findall(text):
            if kind.lower() == "listing" and _field(body, "type").lower() not in ("see", "do", "eat", "drink", "sleep"):
                continue
            name = _field(body, "name")
            if not name:
                continue
            content = _field(body, "content")
            first = re.split(r"(?<=[.!?])\s", re.sub(r"'''?|<[^>]+>", "", content), maxsplit=1)[0][:160]
            items.append({"name": name, "kind": (kind if kind.lower() != "listing" else _field(body, "type")).lower(),
                          "blurb": first, "price": _field(body, "price")[:80],
                          "lat": _field(body, "lat"), "lon": _field(body, "long"), "text": content[:600],
                          "adult": bool(re.search(r"go-?go|ladyboy|girly|hostess|\bstrip", content, re.I))})
        lead = re.sub(r"\{\{.*?\}\}|\[\[(?:File|Image):.*?\]\]|'''?", "", text.split("\n==", 1)[0], flags=re.S)
        lead = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", lead).strip()
        return Result(ok=True, data={"items": items, "lead": lead[:600], "go_next": _go_next(text),
                                     "destinations": destinations(text), "text": text[:120000],
                                     "title": js["parse"]["title"]}, source_url=url)
    return cache.cached("places:wikivoyage", {"page": page, "v": 7}, go)


_WLINK = re.compile(r"\[\[([^|\]#]+)(?:\|([^\]]+))?\]\]")


def destinations(text: str) -> list[dict]:
    """Region/country articles list their 'Cities' and 'Other destinations' as [[links]]."""
    out, seen = [], set()
    for sec in re.finditer(r"==\s*(Cities|Other destinations|Regions)\s*==(.*?)(?=\n==[^=]|\Z)", text, re.S):
        kind = {"Cities": "city", "Other destinations": "destination", "Regions": "region"}[sec.group(1)]
        for line in sec.group(2).splitlines():
            m = _WLINK.search(line)
            if not m or not line.lstrip().startswith(("*", "{{")):
                continue
            page = m.group(1).strip()
            if page.lower() in seen or ":" in page:
                continue
            seen.add(page.lower())
            rest = line[m.end():].split("}}")[-1]
            rest = _WLINK.sub(lambda x: x.group(2) or x.group(1), re.sub(r"\{\{[^{}]*\}\}|'{2,3}", "", rest))
            out.append({"page": page, "name": (m.group(2) or page).strip(), "kind": kind,
                        "blurb": rest.strip(" -\u2013\u2014:*|}").strip()[:200]})
    return out


def _section(text: str, title: str) -> str:
    m = re.search(rf"==\s*{title}\s*==(.*?)(?=\n==[^=]|\Z)", text, re.S | re.I)
    return m.group(1) if m else ""


def guide(name: str) -> dict:
    """Stay districts, highlights and a stay centre for a stop, only from its Wikivoyage article.
    {'found': False} when there is no article: callers say 'no guide article found', nothing is invented."""
    w = wikivoyage(name)
    if not w.ok:
        return {"found": False, "url": w.source_url}
    text = w.data.get("text", "")
    areas = []
    for line in _section(text, "Districts").splitlines():
        m = _WLINK.search(line)
        if m and line.lstrip().startswith(("*", "{{")) and ":" not in m.group(1):
            rest = _WLINK.sub(lambda x: x.group(2) or x.group(1), re.sub(r"\{\{[^{}]*\}\}|'{2,3}", "", line[m.end():]))
            areas.append([(m.group(2) or m.group(1)).strip(), rest.strip(" -\u2013\u2014:*|}").strip()[:200]])
    items = w.data["items"]
    sleep_pts = []
    for i in items:
        if i["kind"] == "sleep" and i.get("lat") and i.get("lon"):
            try:
                sleep_pts.append((float(i["lat"]), float(i["lon"])))
            except ValueError:
                pass
    center = [sum(p[0] for p in sleep_pts) / len(sleep_pts), sum(p[1] for p in sleep_pts) / len(sleep_pts)] if sleep_pts else None
    hl = [i["name"] for i in items if i["kind"] in ("see", "do")][:5]
    return {"found": True, "url": w.source_url, "areas": areas[:5], "highlights": hl, "stay_center": center}


def _go_next(text: str) -> list[str]:
    m = re.search(r"==\s*Go next\s*==(.*?)(?:\n==[^=]|\Z)", text, re.S)
    return re.findall(r"\[\[([^|\]#]+)", m.group(1)) if m else []


def stop_places(stop: dict, diets: tuple = (), n: int = 8) -> dict:
    """{'diet': {pref: [...]}, 'nightlife': [...], 'sights': [...], 'sources': [...], 'ok': bool} for one stop."""
    lat, lon = (stop.get("stay_center") or [stop["lat"], stop["lon"]])
    ov = overpass(lat, lon, 8000 if stop.get("access") else 5000, diets)
    pages = stop.get("wikivoyage") or [stop["name"]]
    wvs = [wikivoyage(pg) for pg in ([pages] if isinstance(pages, str) else pages)]
    wv = next((w for w in wvs if w.ok), wvs[0])
    sights = []
    allitems = [i for w in wvs if w.ok for i in w.data["items"]]
    items = sorted([i for i in allitems if i["kind"] in ("see", "do")], key=lambda i: i["kind"] != "see")
    wv_diet = {d: [{"name": i["name"], "kind": f"{d} (Wikivoyage)", "blurb": i["blurb"], "src": "wikivoyage"}
                   for i in allitems if i["kind"] == "eat" and re.search(DIETS[d][1], i.get("text", ""), re.I)]
               for d in diets}
    wv_drink = [{"name": i["name"], "kind": "bar (Wikivoyage)", "blurb": i["blurb"], "src": "wikivoyage"}
                for i in allitems if i["kind"] == "drink" and not i.get("adult")]
    sights += [{"name": i["name"], "kind": i["kind"], "blurb": i["blurb"], "src": "wikivoyage"} for i in items]
    if ov.ok:
        names = {s["name"].lower() for s in sights}
        sights += [dict(s, src="osm") for s in ov.data["sights"] if s["name"].lower() not in names]
    diet = {d: ((ov.data["diet"].get(d) if ov.ok else []) or wv_diet[d])[:n] for d in diets}
    night = (ov.data["nightlife"] if ov.ok else []) or wv_drink
    return {"diet": diet, "nightlife": night[:n],
            "sights": sights[:n], "ok": ov.ok or wv.ok, "lead": wv.data["lead"] if wv.ok else "",
            "sources": [{"label": "OpenStreetMap Overpass", "ok": ov.ok, "url": ov.source_url, "error": ov.error,
                         "fetched_at": ov.fetched_at},
                        {"label": "Wikivoyage", "ok": wv.ok, "url": wv.source_url, "error": wv.error,
                         "fetched_at": wv.fetched_at}]}
