"""`dayGuide` section: a day-by-day guide with hour-by-hour timelines, named places, transport, meals, backups and budgets.

The author writes places and prices in the local currency; this module only does the sums and the links:
  * `fx` {"from": local currency, "to": home currency, "rate": number, "date": "...", "source": url} converts every `cost` ([lo, hi] or a number).
  * every place gets a Google Maps search link built from `name` + `area` unless it carries its own `maps`.
  * every URL must be https; every day needs a timeline whose times are HH:MM and never run backwards (a small hour after 18:00 is next-day).
  * an item is "unverified" unless it says `verified: true`; the page shows that badge, so research that was not read stays visibly open.
Nothing here knows a place, a currency or a price.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def maps_url(name: str, area: str = "") -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name} {area}".strip())


def _range(c):
    """cost -> (lo, hi) or None. Accepts 120, [80, 150] or None."""
    if c in (None, "", []):
        return None
    if isinstance(c, (int, float)) and not isinstance(c, bool):
        return (c, c)
    if isinstance(c, (list, tuple)) and len(c) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in c) and c[0] <= c[1]:
        return (c[0], c[1])
    raise ValueError(f"cost must be a number or [low, high], got {c!r}")


def _money(cur: str, lo, hi) -> str:
    f = lambda x: f"{round(x):,}"
    return f"{cur} {f(lo)}" if lo == hi else f"{cur} {f(lo)}-{f(hi)}"


def _priced(fx: dict, c) -> dict | None:
    """-> {"lo", "hi", "label"} with the home-currency conversion, or None when there is no cost."""
    r = _range(c)
    if r is None:
        return None
    lo, hi = r
    rate = fx["rate"]
    return {"lo": lo, "hi": hi, "home_lo": round(lo * rate), "home_hi": round(hi * rate),
            "label": f"{_money(fx['from'], lo, hi)} (≈{_money(fx['to'], lo * rate, hi * rate)})"}


def _url(u, where: str) -> str:
    if u and not re.match(r"^https://[^\s]+$", str(u)):
        raise ValueError(f"{where}: link must be https, got {u!r}")
    return u


def _item(it: dict, fx: dict, where: str) -> dict:
    if not isinstance(it, dict):
        raise ValueError(f"{where}: expected an object")
    out = dict(it)
    if out.get("name"):
        out["maps"] = _url(out.get("maps"), where) or maps_url(out["name"], out.get("area", ""))
    for k in ("url", "src", "maps"):
        if out.get(k):
            _url(out[k], f"{where}.{k}")
    for k in ("cost", "entry", "drinks"):
        if k in out:
            p = _priced(fx, out[k]); out[k + "_p"] = p
    h = out.get("how")
    if isinstance(h, dict):
        h = dict(h); h["cost_p"] = _priced(fx, h.get("cost")); out["how"] = h
    if isinstance(out.get("order"), list):
        out["order"] = [{**o, "cost_p": _priced(fx, o.get("cost"))} if isinstance(o, dict) else o for o in out["order"]]
    out["verified"] = out.get("verified") is True
    return out


def _clock(t: str, where: str) -> int:
    if not _TIME.match(str(t)):
        raise ValueError(f"{where}: time must be HH:MM, got {t!r}")
    return int(t[:2]) * 60 + int(t[3:])


def _day(d: dict, fx: dict, n: int) -> dict:
    w = f"day {n + 1}"
    if not d.get("date") or not d.get("title"):
        raise ValueError(f"{w}: needs date and title")
    out = dict(d)
    tl = d.get("timeline") or []
    if not tl:
        raise ValueError(f"{w}: needs a timeline")
    prev, day_shift = -1, 0
    for i, row in enumerate(tl):
        m = _clock(row.get("time"), f"{w} timeline[{i}]")
        if m + day_shift * 1440 < prev and m < 240 and prev >= 18 * 60:   # a small hour after the evening is next day
            day_shift = 1
        if m + day_shift * 1440 < prev:
            raise ValueError(f"{w} timeline[{i}]: {row.get('time')} comes before the row above")
        prev = m + day_shift * 1440
        if row.get("end"):
            _clock(row["end"], f"{w} timeline[{i}].end")
        if not row.get("title"):
            raise ValueError(f"{w} timeline[{i}]: needs a title")
    for key in ("timeline", "eat", "nightlife", "do"):
        out[key] = [_item(x, fx, f"{w} {key}[{i}]") for i, x in enumerate(d.get(key) or [])]
    bk = d.get("backup")
    if bk:
        out["backup"] = {**bk, "items": [_item(x, fx, f"{w} backup[{i}]") for i, x in enumerate(bk.get("items") or [])]}
    out["book"] = [{**b, "u": _url(b.get("u"), f"{w} book[{i}]")} for i, b in enumerate(d.get("book") or [])]
    for i, b in enumerate(out["book"]):
        if not b.get("u") or not b.get("t"):
            raise ValueError(f"{w} book[{i}]: needs t and u")
    bud = d.get("budget")
    if bud:
        rows, lo, hi = [], 0, 0
        for i, r in enumerate(bud.get("rows") or []):
            p = _priced(fx, r.get("cost")) if "cost" in r else None
            if "home" in r:   # a row already in the home currency
                a, b = (r["home"] if isinstance(r["home"], list) else [r["home"], r["home"]])
                p = {"home_lo": a, "home_hi": b, "label": _money(fx["to"], a, b)}
            if not p:
                raise ValueError(f"{w} budget[{i}]: needs cost (local) or home")
            lo += p["home_lo"]; hi += p["home_hi"]
            rows.append({**r, "p": p})
        out["budget"] = {**bud, "rows": rows, "total": {"lo": lo, "hi": hi, "label": _money(fx["to"], lo, hi)}}
    return out


def process(raw: dict) -> dict:
    fx = raw.get("fx") or {}
    for k in ("from", "to", "rate", "date"):
        if not fx.get(k):
            raise ValueError(f"fx.{k} is required (currency conversions are dated and sourced, never implied)")
    if not isinstance(fx["rate"], (int, float)) or fx["rate"] <= 0:
        raise ValueError("fx.rate must be a positive number")
    _url(fx.get("source"), "fx.source")
    days = raw.get("days") or []
    if not days:
        raise ValueError("days is empty")
    out = {**raw, "days": [_day(d, fx, i) for i, d in enumerate(days)]}
    out["trip_total"] = {"lo": sum(d["budget"]["total"]["lo"] for d in out["days"] if d.get("budget")),
                         "hi": sum(d["budget"]["total"]["hi"] for d in out["days"] if d.get("budget"))}
    return out
