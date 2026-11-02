"""Render plan.json -> single self-contained HTML (+ optional PNG)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TPL = Path(__file__).resolve().parent / "templates"
SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "THB": "฿"}


def _money(n, ccy="INR"):
    if n is None:
        return "unavailable"
    return f"{SYMBOLS.get(ccy, ccy + ' ')}{int(n):,}"


def _dur(m):
    return "" if not m else f"{m // 60}h {m % 60:02d}m"


def _day(s):
    return dt.date.fromisoformat(s).strftime("%a %d %b")


def _short(s):
    return dt.date.fromisoformat(s).strftime("%d %b")


def day_plan(opt: dict) -> list[dict]:
    """Day-by-day bullets from stop highlights + flight times. Highlights are curated static text, not fetched."""
    out = []
    legs = opt["legs"]
    for i, s in enumerate(opt["stops"]):
        arr = legs[i]
        pick = arr["rows"][0] if arr["rows"] else None
        hl = list(s["highlights"]) or [f"Explore {s['name']}"]
        d0 = dt.date.fromisoformat(s["checkin"])
        for k in range(s["nights"]):
            d = d0 + dt.timedelta(days=k)
            text = hl[k % len(hl)]
            if k == 0 and pick:
                text = f"Arrive {pick['arr']} on {pick['flight']}. " + text
            elif k == 0:
                text = f"Arrive {s['name']}. " + text
            out.append({"date": d.strftime("%a %d %b"), "place": s["name"], "text": text})
    last = legs[-1]
    p = last["rows"][0] if last["rows"] else None
    out.append({"date": dt.date.fromisoformat(last["date"]).strftime("%a %d %b"), "place": "Return",
                "text": f"Fly home {p['flight']} {p['dep']} from {last['orig']}." if p else f"Fly home from {last['orig']}."})
    return out


def build_env():
    env = Environment(loader=FileSystemLoader(str(TPL)), autoescape=select_autoescape(["html"]))
    env.filters.update(dur=_dur, day=_day, short=_short)
    return env


def decision(plan: dict) -> dict:
    m = plan["meta"]
    opts = [o for o in plan["options"]]
    full = [o for o in opts if not o["totals"]["flight_legs_missing"] and not o["totals"]["stays_missing"]]
    best = min(full, key=lambda o: o["totals"]["core_pp"]) if full else None
    return {"best": best, "n_full": len(full)}


def render_html(plan: dict, out_html: Path) -> Path:
    env = build_env()
    ccy = plan["meta"]["currency"]
    env.filters["money"] = lambda n: _money(n, ccy)
    for o in plan["options"]:
        o["days_plan"] = day_plan(o)
    hero = None
    for ph in plan["photos"].values():
        if ph:
            hero = ph[0]
            break
    html = env.get_template("plan.html.j2").render(plan=plan, hero=hero, dec=decision(plan), m=plan["meta"])
    out_html.write_text(html, encoding="utf-8")
    return out_html


def render_png(html_path: Path, png_path: Path) -> Path:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = None
        for kw in ({"channel": "chrome"}, {}):
            try:
                b = p.chromium.launch(headless=True, **kw)
                break
            except Exception:  # noqa: BLE001
                continue
        if not b:
            raise RuntimeError("no Chrome/Chromium available for PNG rendering")
        pg = b.new_page(viewport={"width": 1000, "height": 1200}, device_scale_factor=2)
        pg.goto(html_path.resolve().as_uri())
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(png_path), full_page=True)
        b.close()
    return png_path


def render(plan_json: Path, png: bool = True) -> tuple[Path, Path | None]:
    plan = json.loads(plan_json.read_text())
    html = render_html(plan, plan_json.parent / "plan.html")
    return html, (render_png(html, plan_json.parent / "plan.png") if png else None)
