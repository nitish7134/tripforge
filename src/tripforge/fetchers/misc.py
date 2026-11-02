"""Keyless fetchers: FX, advisory, climate, weather. Visa lives in visa.py."""
from __future__ import annotations

import datetime as dt
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .common import Result, client, fail, save_json

def fetch_fx(src: str, dst: str, evid: Path) -> Result:
    if src == dst:
        return Result(ok=True, data={"rate": 1.0, "date": None, "src": src, "dst": dst}, source_url="")
    url = f"https://api.frankfurter.app/latest?from={src}&to={dst}"
    try:
        with client() as c:
            j = c.get(url).json()
        rate = j["rates"][dst]
        save_json(evid / f"fx_{src}-{dst}.json", j)
        return Result(ok=True, data={"rate": rate, "date": j.get("date"), "src": src, "dst": dst},
                      source_url=url, screenshot_path=str(evid / f"fx_{src}-{dst}.json"))
    except Exception as e:  # noqa: BLE001
        return fail(str(e), url)


_RSS = "https://travel.state.gov/_res/rss/TAsTWs.xml"


def fetch_advisories(countries: dict[str, str], evid: Path) -> dict[str, Result]:
    """countries: cc -> country name. One RSS download, matched per country."""
    try:
        with client() as c:
            xml = c.get(_RSS).text
        (evid / "advisories_rss.xml").write_text(xml)
        items = [(i.findtext("title") or "", i.findtext("link") or "") for i in ET.fromstring(xml).iter("item")]
    except Exception as e:  # noqa: BLE001
        return {cc: fail(str(e), _RSS) for cc in countries}
    out = {}
    for cc, name in countries.items():
        hit = next(((t, l) for t, l in items if t.lower().startswith(name.lower() + " -")), None)
        if hit:
            m = re.search(r"Level (\d)", hit[0])
            out[cc] = Result(ok=True, data={"title": hit[0], "level": int(m.group(1)) if m else None},
                             source_url=hit[1] or _RSS, screenshot_path=str(evid / "advisories_rss.xml"))
        else:
            out[cc] = fail(f"{name} not found in US State Dept feed", _RSS)
    return out


def fetch_climate(iata: str, month: int, evid: Path) -> Result:
    url = "https://sunshineatlas.com/api/mcp"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_destination_climate", "arguments": {"destination": iata}}}
    try:
        with client(30) as c:
            r = c.post(url, json=body, headers={"accept": "application/json, text/event-stream"})
        txt = r.text
        if txt.lstrip().startswith("event:") or "\ndata:" in txt:
            txt = [l[5:] for l in txt.splitlines() if l.startswith("data:")][0]
        card = json.loads(json.loads(txt)["result"]["content"][0]["text"])
        save_json(evid / f"climate_{iata}.json", card)
        d = card["destination"]
        m = d["monthly"][month - 1]
        return Result(ok=True, data={
            "city": d["city"], "month": m["month"], "day_high_c": m["dayHighC"], "night_low_c": m["nightLowC"],
            "rain_mm": m["rainMm"], "uv": m["middayUvIndex"], "uv_cat": m["middayUvCategory"],
            "sea_c": m.get("seaTempC"), "score": m["sunshineScore"], "best_month": d.get("bestMonth"),
            "climate": d.get("climate")}, source_url=d.get("url") or url,
            screenshot_path=str(evid / f"climate_{iata}.json"))
    except Exception as e:  # noqa: BLE001
        return fail(str(e), url)


def fetch_weather(lat: float, lon: float, start: str, end: str, evid: Path, tag: str) -> Result:
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto&forecast_days=16")
    s = dt.date.fromisoformat(start)
    if (s - dt.date.today()).days > 15:
        return fail("trip is beyond the 16-day forecast window; see climate normals instead", url)
    try:
        with client() as c:
            j = c.get(url).json()
        save_json(evid / f"weather_{tag}.json", j)
        d = j["daily"]
        rows = [{"date": a, "max": b, "min": c_, "rain": r} for a, b, c_, r in
                zip(d["time"], d["temperature_2m_max"], d["temperature_2m_min"], d["precipitation_sum"])
                if start <= a <= end]
        return Result(ok=bool(rows), data=rows, source_url=url, screenshot_path=str(evid / f"weather_{tag}.json"))
    except Exception as e:  # noqa: BLE001
        return fail(str(e), url)
