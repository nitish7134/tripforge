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
    hero = None
    for ph in plan["photos"].values():
        if ph:
            hero = ph[0]
            break
    html = env.get_template("plan.html.j2").render(plan=plan, hero=hero, dec=decision(plan), m=plan["meta"])
    out_html.write_text(html, encoding="utf-8")
    return out_html


def render_pdf_png(html_path: Path, pdf_path: Path, png_path: Path | None) -> tuple[Path | None, Path | None]:
    """One headless browser: A4 PDF (print CSS, backgrounds on) always, full-page PNG optionally."""
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
            raise RuntimeError("no Chrome/Chromium available for PDF/PNG rendering")
        pg = b.new_page(viewport={"width": 1000, "height": 1200}, device_scale_factor=2)
        pg.goto(html_path.resolve().as_uri())
        pg.wait_for_timeout(400)
        pg.pdf(path=str(pdf_path), format="A4", print_background=True,
               margin={"top": "10mm", "bottom": "10mm", "left": "8mm", "right": "8mm"})
        if png_path:
            pg.emulate_media(media="screen")
            pg.screenshot(path=str(png_path), full_page=True)
        b.close()
    return pdf_path, png_path


def render(plan_json: Path, png: bool = True) -> list[Path | None]:
    plan = json.loads(plan_json.read_text())
    html = render_html(plan, plan_json.parent / "plan.html")
    pdf, pngp = render_pdf_png(html, plan_json.parent / "plan.pdf", plan_json.parent / "plan.png" if png else None)
    return [html, pdf, pngp]
