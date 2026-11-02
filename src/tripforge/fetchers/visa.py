"""Visa requirements for (passport country, destination country), read live from Wikipedia.

Source: the community-maintained article "Visa requirements for <Demonym> citizens" (keyless MediaWiki API).
Nothing is hardcoded per passport or destination; results are cached 30 days (cache "visa").
"""
from __future__ import annotations

import re
import time
from urllib.parse import quote

from .. import cache
from .common import Result, client, fail

API = "https://en.wikipedia.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
VERIFY = "Check the embassy/official source before booking; Wikipedia is community-maintained."


def article_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="_(),:'")


# ---------------------------------------------------------------- wikitext helpers
_STATUS_TPL = {"yes", "yes2", "no", "no2", "partial", "optional", "maybe", "unknown", "n/a", "na", "dunno"}


def _tpl(m: re.Match) -> str:
    parts = m.group(1).split("|")
    name = parts[0].strip().lower()
    if (name in _STATUS_TPL or name.startswith("flag")) and len(parts) > 1:
        return parts[1].strip()
    if name in ("nowrap", "small", "abbr") and len(parts) > 1:
        return parts[1].strip()
    return ""


def clean(s: str) -> str:
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", "; ", s)
    s = re.sub(r"<[^>]+>", "", s)
    for _ in range(6):
        n = re.sub(r"\{\{([^{}]*)\}\}", _tpl, s)
        if n == s:
            break
        s = n
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+ ([^\]]+)\]", r"\1", s)
    s = re.sub(r"\[https?://\S+\]", "", s)
    s = s.replace("'''", "").replace("''", "")
    s = re.sub(r'^\s*(?:data-sort-value|style|class|rowspan|colspan)="[^"]*"\s*\|?\s*', "", s)
    s = re.sub(r'(?:data-sort-value|style)="[^"]*"', "", s)
    return re.sub(r"[ \t]+", " ", s).strip(" \n\t|")


def normalise_status(raw: str) -> str:
    t = raw.lower()
    if re.search(r"not required|visa[- ]free|freedom of movement|no visa", t):
        return "visa not required"
    if re.search(r"e-?visa|electronic|online visa", t):
        return "eVisa"
    if "on arrival" in t:
        return "visa on arrival"
    if "visa required" in t or t.startswith("visa"):
        return "visa required"
    return "other"


def _cells(chunk: str) -> list[str]:
    cells: list[list[str]] = []
    for line in chunk.split("\n"):
        if line.startswith("|") and not line.startswith(("|}", "|-", "|+")):
            cells.append([line[1:]])
        elif cells:
            cells[-1].append(line)
    return ["\n".join(c) for c in cells]


def find_row(wikitext: str, names: set[str], dest_iso2: str = "") -> dict | None:
    """First table row for the destination: its Timatic reference names `dest_iso2`, or its first cell is one of
    `names` (lower-case). -> {status_raw, stay, notes}."""
    for chunk in re.split(r"\n\|-[^\n]*", wikitext):
        cells = _cells(chunk)
        if len(cells) < 2:
            continue
        by_code = bool(dest_iso2) and f"destination={dest_iso2}" in cells[1] and "flag" in cells[0].lower()
        if not by_code and clean(cells[0]).lower() not in names:
            continue
        status_raw = clean(cells[1])
        if not status_raw:
            continue
        stay = clean(cells[2]) if len(cells) > 2 else ""
        notes_raw = "\n".join(cells[3:]) if len(cells) > 3 else ""
        bits = (clean(l.lstrip("*# ").strip()).replace("✓", "").strip().rstrip(".;") for l in notes_raw.split("\n"))
        notes = "; ".join(x for x in bits if x)
        if len(notes) > 400:
            notes = notes[:397].rstrip() + "..."
        return {"status_raw": status_raw, "stay": stay, "notes": notes}
    return None


# ---------------------------------------------------------------- network
def _country(c, iso2: str) -> dict | None:
    """Wikidata (keyless SPARQL): English label, alt labels and demonyms for an ISO 3166-1 alpha-2 code."""
    q = ('SELECT ?l ?a ?d WHERE { ?c wdt:P297 "%s". ?c rdfs:label ?l. FILTER(lang(?l)="en") '
         'OPTIONAL { ?c skos:altLabel ?a. FILTER(lang(?a)="en") } '
         'OPTIONAL { ?c wdt:P1549 ?d. FILTER(lang(?d)="en") } }' % iso2)
    rows = c.get(SPARQL, params={"query": q, "format": "json"}).json()["results"]["bindings"]
    if not rows:
        return None
    vals = lambda k: sorted({r[k]["value"] for r in rows if k in r})  # noqa: E731
    return {"iso2": iso2, "name": rows[0]["l"]["value"], "alt": vals("a"), "demonyms": vals("d")}


def _wikitext(c, title: str) -> tuple[str, str, int] | None:
    j = c.get(API, params={"action": "parse", "page": title, "prop": "wikitext|revid", "format": "json",
                           "redirects": 1}).json()
    p = j.get("parse")
    if not p:
        return None
    return p["title"], p["wikitext"]["*"], p["revid"]


def _is_for(text: str, iso2: str) -> bool:
    """The article's Timatic references name its passport country; accept when absent (small articles)."""
    codes = set(re.findall(r"nationality=([A-Z]{2})", text))
    return not codes or iso2 in codes


def _article(c, pc: dict) -> tuple[str, str, int] | None:
    for dem in pc["demonyms"]:
        got = _wikitext(c, f"Visa requirements for {dem} citizens")
        if got and _is_for(got[1], pc["iso2"]):
            return got
    name = pc["name"]
    for pre in dict.fromkeys([name, name[:7], name[:5]]):
        j = c.get(API, params={"action": "opensearch", "search": f"Visa requirements for {pre}", "limit": 8,
                               "format": "json"}).json()
        for t in j[1]:
            if t.lower().startswith("visa requirements for") and "citizens" in t.lower():
                got = _wikitext(c, t)
                if got and _is_for(got[1], pc["iso2"]):
                    return got
    return None


def _go(passport: str, dest: str) -> Result:
    url = ""
    try:
        with client(40) as c:
            pc = _country(c, passport)
            dc = _country(c, dest)
            if not pc or not dc:
                return fail(f"unknown country code {passport if not pc else dest}")
            if pc["demonyms"]:
                url = article_url(f"Visa requirements for {pc['demonyms'][0]} citizens")
            got = _article(c, pc)
            if got is None:
                return fail(f"no Wikipedia visa-requirements article found for passport {passport}", url)
            title, text, revid = got
            url = article_url(title)
            names = {n.lower() for n in [dc["name"], *dc["alt"]] if len(n) > 2}
            row = find_row(text, names, dest)
            ts = ""
            try:
                q = c.get(API, params={"action": "query", "prop": "revisions", "rvprop": "ids|timestamp",
                                       "revids": revid, "format": "json"}).json()
                ts = next(iter(q["query"]["pages"].values()))["revisions"][0]["timestamp"]
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        return fail(f"could not read Wikipedia: {e}", url)
    if not row:
        return fail(f"{dc['name']} not found in '{title}'", url)
    return Result(ok=True, source_url=url, fetched_at=time.time(), data={
        "passport": passport, "dest": dest, "status": normalise_status(row["status_raw"]),
        "status_raw": row["status_raw"], "stay": row["stay"], "notes": row["notes"],
        "revid": revid, "revision_ts": ts, "article": title, "verify": VERIFY})


def visa_requirement(passport_iso2: str, dest_iso2: str) -> Result:
    p, d = passport_iso2.strip().upper(), dest_iso2.strip().upper()
    if p == d:
        return fail("domestic trip, no visa needed")
    return cache.cached("visa", {"p": p, "d": d, "v": 1}, lambda: _go(p, d))
