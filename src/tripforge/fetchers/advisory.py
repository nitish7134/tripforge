"""Travel advisories chosen by the traveller's PASSPORT country, never US-only.

Source list keyed by passport ISO2 (all keyless):
  GB -> FCDO foreign travel advice (GOV.UK content API)
  US -> US State Department RSS
  CA -> Government of Canada travel advisories (data.international.gc.ca)
  any other passport -> FCDO + US together, labelled as third-country advisories.
Each country's Result.data is {'entries': [{'source','tag','text','url','error'}], 'own': bool, 'note': str|None}.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import cache
from .common import Result, client, fail, save_json

FCDO = "https://www.gov.uk/api/content/foreign-travel-advice/{slug}"
US_RSS = "https://travel.state.gov/_res/rss/TAsTWs.xml"
CA_JSON = "https://data.international.gc.ca/travel-voyage/index-updated.json"
CA_STATE = {0: "Take normal security precautions", 1: "Exercise a high degree of caution",
            2: "Avoid non-essential travel", 3: "Avoid all travel"}
SOURCES = {"GB": ["FCDO"], "US": ["US"], "CA": ["CA"]}
THIRD_COUNTRY = ["FCDO", "US"]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _fcdo(name: str, evid: Path) -> dict:
    url = FCDO.format(slug=_slug(name))
    try:
        with client(20) as c:
            r = c.get(url)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        j = r.json()
        status = [s.replace("_", " ") for s in (j.get("details", {}).get("alert_status") or [])]
        return {"source": "UK FCDO", "tag": "; ".join(status) or "no warning flags", "text": j.get("title", name),
                "url": f"https://www.gov.uk/foreign-travel-advice/{_slug(name)}", "updated": (j.get("public_updated_at") or "")[:10]}
    except Exception as e:  # noqa: BLE001
        return {"source": "UK FCDO", "error": f"unavailable: {type(e).__name__} {e}", "url": url}


_us_cache: dict = {}


def _us(name: str, evid: Path) -> dict:
    try:
        if "items" not in _us_cache:
            with client(25) as c:
                xml = c.get(US_RSS).text
            (evid / "advisories_rss.xml").write_text(xml)
            _us_cache["items"] = [(i.findtext("title") or "", i.findtext("link") or "") for i in ET.fromstring(xml).iter("item")]
        hit = next(((t, l) for t, l in _us_cache["items"] if t.lower().startswith(name.lower() + " -")), None)
        if not hit:
            return {"source": "US State Department", "error": f"{name} not found in the feed", "url": US_RSS}
        m = re.search(r"Level (\d)", hit[0])
        return {"source": "US State Department", "tag": f"Level {m.group(1)}" if m else "", "level": int(m.group(1)) if m else None,
                "text": hit[0].split(" - ", 1)[-1], "url": hit[1] or US_RSS}
    except Exception as e:  # noqa: BLE001
        return {"source": "US State Department", "error": f"unavailable: {type(e).__name__}", "url": US_RSS}


_ca_cache: dict = {}


def _ca(name: str, cc: str, evid: Path) -> dict:
    try:
        if "data" not in _ca_cache:
            with client(40) as c:
                _ca_cache["data"] = c.get(CA_JSON).json()["data"]
            save_json(evid / "advisories_ca_meta.json", {"source": CA_JSON})
        d = _ca_cache["data"].get(cc)
        if not d:
            return {"source": "Government of Canada", "error": f"{name} not in the feed", "url": CA_JSON}
        e = d.get("eng") or {}
        return {"source": "Government of Canada", "tag": CA_STATE.get(d.get("advisory-state"), "see page"),
                "text": e.get("name", name), "url": "https://travel.gc.ca/destinations/" + e.get("url-slug", "")}
    except Exception as e:  # noqa: BLE001
        return {"source": "Government of Canada", "error": f"unavailable: {type(e).__name__}", "url": CA_JSON}


def fetch_advisories(passport: str, countries: dict[str, str], evid: Path) -> dict[str, Result]:
    """countries: cc -> country name. One Result per country, sources chosen by `passport`."""
    keys = SOURCES.get(passport.upper())
    own = keys is not None
    keys = keys or THIRD_COUNTRY
    note = None if own else "third-country advisories (your government's page not integrated)"
    out = {}
    for cc, name in countries.items():
        entries = []
        for k in keys:
            entries.append(_fcdo(name, evid) if k == "FCDO" else _us(name, evid) if k == "US" else _ca(name, cc, evid))
        ok = any("error" not in e for e in entries)
        url = next((e["url"] for e in entries if "error" not in e), entries[0]["url"])
        r = Result(ok=ok, data={"entries": entries, "own": own, "note": note}, source_url=url,
                   error=None if ok else "; ".join(e.get("error", "") for e in entries))
        out[cc] = r
    return out
