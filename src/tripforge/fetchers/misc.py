"""Keyless fetchers: FX and short-range weather. Advisory lives in advisory.py, climate normals in climate.py, visa in visa.py."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .common import Result, client, fail, save_json

def fetch_fx(src: str, dst: str, evid: Path) -> Result:
    if src == dst:
        return Result(ok=True, data={"rate": 1.0, "date": None, "src": src, "dst": dst}, source_url="")
    url = f"https://api.frankfurter.dev/v1/latest?base={src}&symbols={dst}"
    try:
        with client() as c:
            j = c.get(url).json()
        rate = j["rates"][dst]
        save_json(evid / f"fx_{src}-{dst}.json", j)
        return Result(ok=True, data={"rate": rate, "date": j.get("date"), "src": src, "dst": dst},
                      source_url=url, screenshot_path=str(evid / f"fx_{src}-{dst}.json"))
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
