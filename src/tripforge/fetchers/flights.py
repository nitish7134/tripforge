"""Google Flights one-way nonstop fetcher. Parses expanded 'Flight details' cards (flight numbers included)."""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from .common import Result, fail

EXPAND_JS = """async () => {
  const bs = [...document.querySelectorAll('button[aria-label^="Flight details"]')].slice(0, 12);
  for (const b of bs) { try { b.click(); } catch (e) {} await new Promise(r => setTimeout(r, 250)); }
  await new Promise(r => setTimeout(r, 900));
  return document.body.innerText;
}"""

_PRICE = re.compile(r"^\s*([₹$€£]|[A-Z]{3})\s?([\d,]+)\s*$", re.M)
_TIME = re.compile(r"(\d{1,2}:\d{2}\s?[AP]M)(\s*\+\d)?\s*([^\n]*?)\(([A-Z]{3})\)")
_DUR = re.compile(r"Travel time:\s*(?:(\d+)\s*hr)?\s*(?:(\d+)\s*min)?")
_FNO = re.compile(r"^(.*?)(Economy|Premium economy|Business|First)(.*?)([A-Z0-9]{2})[ \u00a0](\d{1,4})\s*$", re.M)


def parse_flights(text: str) -> list[dict]:
    out, seen = [], set()
    for blk in text.split("Select flight")[1:]:
        pm, tm, fm = _PRICE.search(blk), _TIME.findall(blk), _FNO.search(blk)
        if not (pm and len(tm) >= 2 and fm):
            continue
        d = _DUR.search(blk)
        mins = (int(d.group(1) or 0) * 60 + int(d.group(2) or 0)) if d else None
        code, num = fm.group(4), fm.group(5)
        key = (code, num)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "airline": fm.group(1).strip(), "aircraft": fm.group(3).strip(),
            "flight": f"{code} {num}",
            "from": tm[0][3], "to": tm[1][3],
            "dep": tm[0][0].replace(" ", ""), "arr": tm[1][0].replace(" ", ""),
            "next_day": bool(tm[1][1].strip()) if tm[1][1] else False,
            "duration_min": mins,
            "price": int(pm.group(2).replace(",", "")), "currency_symbol": pm.group(1),
        })
    out.sort(key=lambda f: f["price"])
    return out


def flight_url(orig: str, dest: str, date: str, currency: str) -> str:
    q = f"Flights from {orig} to {dest} on {date} nonstop one way"
    return ("https://www.google.com/travel/flights?q=" + urllib.parse.quote(q) +
            f"&curr={currency}&hl=en")


def fetch_leg(br, orig: str, dest: str, date: str, currency: str, evid: Path) -> Result:
    url = flight_url(orig, dest, date, currency)
    try:
        br.goto(url, 4500)
        text = br.eval(EXPAND_JS)
    except Exception as e:  # noqa: BLE001
        return fail(f"browser error: {e}", url)
    shot = evid / f"flights_{orig}-{dest}_{date}.png"
    has = br.screenshot(shot)
    rows = parse_flights(text or "")
    # Guard against Google rerouting to another airport pair.
    rows = [r for r in rows if r["from"] == orig and r["to"] == dest] or rows
    r = Result(ok=bool(rows), data=rows, source_url=url, screenshot_path=str(shot) if has else None)
    if not rows:
        r.error = "no nonstop flights parsed (none exist, or page blocked)"
    return r
