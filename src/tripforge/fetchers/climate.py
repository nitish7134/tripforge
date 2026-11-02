"""Monthly climate normals for any lat/lon from Open-Meteo's archive API (keyless).

Averages the trip month over the last N complete years: day highs, night lows, rain days (>= 1 mm), total rain
and sunshine hours. The seasonal warning is derived from these numbers, never hand-written per place.
"""
from __future__ import annotations

import calendar
import datetime as dt

from .. import cache
from .common import Result, client, fail

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
YEARS = 5


def warning(c: dict) -> str:
    bits = []
    rd = c["rain_days"]
    bits.append(f"wet season: {rd} rain days" if rd >= 15 else f"showery: {rd} rain days" if rd >= 8 else f"mostly dry: {rd} rain days")
    if c["day_high_c"] >= 35:
        bits.append(f"very hot days ({c['day_high_c']}\u00b0C)")
    if c["night_low_c"] <= 3:
        bits.append(f"cold nights ({c['night_low_c']}\u00b0C)")
    return "; ".join(bits)


def fetch_normals(lat: float, lon: float, month: int) -> Result:
    def go() -> Result:
        last = dt.date.today().year - 1
        hi, lo, rain, rdays, sun, n = [], [], [], [], [], 0
        url = ARCHIVE
        try:
            with client(30) as c:
                for y in range(last - YEARS + 1, last + 1):
                    end = calendar.monthrange(y, month)[1]
                    params = {"latitude": lat, "longitude": lon, "start_date": f"{y}-{month:02d}-01",
                              "end_date": f"{y}-{month:02d}-{end:02d}", "timezone": "auto",
                              "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,sunshine_duration"}
                    r = c.get(ARCHIVE, params=params)
                    url = str(r.url)
                    d = r.json()["daily"]
                    ok = [i for i, v in enumerate(d["temperature_2m_max"]) if v is not None]
                    if not ok:
                        continue
                    hi.append(sum(d["temperature_2m_max"][i] for i in ok) / len(ok))
                    lo.append(sum(d["temperature_2m_min"][i] for i in ok) / len(ok))
                    pr = [d["precipitation_sum"][i] or 0 for i in ok]
                    rain.append(sum(pr))
                    rdays.append(sum(1 for v in pr if v >= 1.0) * end / len(ok))
                    sh = [d["sunshine_duration"][i] for i in ok if d["sunshine_duration"][i] is not None]
                    if sh:
                        sun.append(sum(sh) / len(sh) / 3600)
                    n += 1
        except Exception as e:  # noqa: BLE001
            return fail(f"open-meteo archive error: {type(e).__name__}", ARCHIVE)
        if not n:
            return fail("open-meteo archive returned no data", ARCHIVE)
        avg = lambda xs: sum(xs) / len(xs)  # noqa: E731
        res = {"month": calendar.month_name[month], "day_high_c": round(avg(hi)), "night_low_c": round(avg(lo)),
               "rain_mm": round(avg(rain)), "rain_days": round(avg(rdays)),
               "sunshine_h": round(avg(sun), 1) if sun else None, "years": n}
        res["warning"] = warning(res)
        return Result(ok=True, data=res, source_url=url)
    return cache.cached("climate:openmeteo", {"lat": round(lat, 2), "lon": round(lon, 2), "m": month, "v": 1}, go)
