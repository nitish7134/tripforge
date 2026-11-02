"""tripforge CLI: brief -> (menu) -> plan. Works for any destination."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import List, Optional

import typer
import yaml
from rich.console import Console

from . import cache
from .plan import PlanError, run_plan
from .render import render as do_render

app = typer.Typer(add_completion=False, help="Minimal-input trip planner for any destination: brief -> menu -> plan (HTML/PDF/PNG).")
console = Console()

BRIEF_KEYS = ("from", "home_city", "stops", "start", "alt_start", "end_airport", "people", "budget_night", "prefs", "currency",
              "passport", "hostels", "meal_rate", "meals_per_day", "party_rate", "party_share", "transport_day",
              "flights_backend", "stays_backend", "browser", "country")


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "trip"


def trip_dir(trip: str | None, brief: Path | None, cfg: dict) -> Path:
    if brief is not None and trip is None:
        return brief.resolve().parent
    slug = trip or slugify(f"{cfg.get('stops', 'trip').split(':')[0]}-{cfg.get('start', '')}")
    return cache.repo_root() / "trips" / slug


def load_brief(path: Path | None) -> dict:
    if not path:
        return {}
    d = yaml.safe_load(path.read_text()) or {}
    if isinstance(d.get("prefs"), str):
        d["prefs"] = [x.strip() for x in d["prefs"].split(",") if x.strip()]
    return d


@app.command()
def plan(
    home: Optional[str] = typer.Option(None, "--from", help="Home airport IATA, e.g. <IATA>; or set home_city in the brief"),
    stops: Optional[str] = typer.Option(None, help='Comma list "City:nights[@IATA]", e.g. "Lisbon:3,Porto:2"'),
    start: Optional[str] = typer.Option(None, help="Start date YYYY-MM-DD"),
    alt_start: Optional[List[str]] = typer.Option(None, "--alt-start", help="Extra start date(s) to compare"),
    end_airport: Optional[str] = typer.Option(None, "--end-airport", help="Fly home from this airport instead of the last stop's"),
    people: Optional[int] = typer.Option(None, help="Travellers (default 2)"),
    budget_night: Optional[int] = typer.Option(None, "--budget-night", help="Stay budget per night, in the trip currency (default: no cap)"),
    prefs: Optional[str] = typer.Option(None, help="Comma list, e.g. veg,party"),
    meal_rate: Optional[int] = typer.Option(None, "--meal-rate", help="Per meal per person (needed for the daily spend section)"),
    party_rate: Optional[int] = typer.Option(None, "--party-rate", help="Per party night per person (needed for party trips)"),
    currency: Optional[str] = typer.Option(None, help="ISO 4217 code (default: the home airport country's currency)"),
    passport: Optional[str] = typer.Option(None, help="Passport country code (default: home airport country)"),
    country: Optional[str] = typer.Option(None, help="Country hint for resolving stop names"),
    trip: Optional[str] = typer.Option(None, "--trip", help="Trip slug: writes trips/<slug>/{brief.yaml,out/,evidence/,notes.md}"),
    brief: Optional[Path] = typer.Option(None, "--brief", help="Read inputs from a brief.yaml (CLI flags override)"),
    flights_backend: Optional[str] = typer.Option(None, "--flights-backend", help="auto (fli, browser fallback) | fli | browser"),
    stays_backend: Optional[str] = typer.Option(None, "--stays-backend", help="auto (pyairbnb, browser fallback) | pyairbnb | browser"),
    browser: Optional[str] = typer.Option(None, help="headless or attach, for browser fallbacks"),
    hostels: bool = typer.Option(False, "--hostels", help="Also search cheap private rooms"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Ignore and do not write the sqlite cache"),
    png: bool = typer.Option(True, "--png/--no-png", help="Also render plan.png (plan.pdf is always written)"),
):
    """Build trips/<slug>/out/{plan.json,plan.html,plan.pdf,plan.png} and trips/<slug>/evidence/."""
    t0 = time.time()
    cache.configure(enabled=not no_cache)
    cfg = load_brief(brief)
    cli = {"from": home, "stops": stops, "start": start, "alt_start": alt_start or None, "end_airport": end_airport,
           "people": people, "budget_night": budget_night,
           "prefs": [x.strip() for x in prefs.split(",") if x.strip()] if prefs is not None else None,
           "meal_rate": meal_rate, "party_rate": party_rate, "currency": currency, "passport": passport,
           "country": country, "flights_backend": flights_backend, "stays_backend": stays_backend,
           "browser": browser, "hostels": hostels or None}
    cfg.update({k: v for k, v in cli.items() if v is not None})
    td = trip_dir(trip, brief, cfg)
    out, evid = td / "out", td / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    evid.mkdir(parents=True, exist_ok=True)
    (td / "brief.yaml").write_text(yaml.safe_dump({k: cfg[k] for k in BRIEF_KEYS if k in cfg}, sort_keys=False,
                                                  allow_unicode=True))
    if not (td / "notes.md").exists():
        (td / "notes.md").write_text(f"# {td.name}\n\nDecisions, bookings and open questions for this trip.\n")
    try:
        p = run_plan(cfg, evid)
    except PlanError as e:
        console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(2)
    p["meta"]["trip"] = td.name
    pj = out / "plan.json"
    pj.write_text(json.dumps(p, indent=1, ensure_ascii=False, default=str))
    files = do_render(pj, png=png)
    console.print(f"[green]done[/green] in {time.time() - t0:.0f}s: " + "  ".join(str(f) for f in files if f))
    console.print(f"backends: flights {p['meta']['backends']['flights']}, stays {p['meta']['backends']['stays']}; "
                  f"cache {p['meta']['cache']}")
    for o in p["options"]:
        t = o["totals"]
        console.print(f"[bold]Option {o['start']}[/bold] core/person {t['core_pp']:,} (missing legs "
                      f"{t['flight_legs_missing']}, stays {t['stays_missing']}); all-in {t['all_in_lo_pp']:,}-{t['all_in_hi_pp']:,}")
        for lg in o["legs"]:
            if lg["kind"] == "ground":
                g = lg["ground"]
                console.print(f"  {lg['date']} {lg['orig']} -> {lg['dest']} {g['mode']} {g['hours'][0]}-{g['hours'][1]}h "
                              f"{(str(g['amount'][0]) + '-' + str(g['amount'][1]) + ' ' + g['currency']) if g.get('amount') else 'price unavailable'} (indicative, {g['source']})")
            elif lg["rows"]:
                for r in lg["rows"][:2]:
                    console.print(f"  {lg['date']} {r['flight']:8} {r['from']} {r['dep']} -> {r['to']} {r['arr']}  "
                                  f"{r['price'] if r['price'] is None else format(r['price'], ',')}  [{lg['backend']}{', cached' if lg['cached'] else ''}]")
            else:
                console.print(f"  {lg['date']} {lg['orig']} -> {lg['dest']} unavailable ({lg['error']})")


@app.command()
def render(plan_json: Path = typer.Argument(..., help="trips/<slug>/out/plan.json"),
           png: bool = typer.Option(False, "--png", help="Also write plan.png")):
    """Re-render plan.html + plan.pdf (and PNG) from an existing plan.json without refetching."""
    files = do_render(plan_json.resolve(), png=png)
    console.print("[green]rendered[/green] " + "  ".join(str(f) for f in files if f))


@app.command()
def menu(brief: Path = typer.Option(..., "--brief", help="brief.yaml with destination, month/start, nights, people, from, prefs, rates"),
         live: bool = typer.Option(True, "--live/--no-live", help="Fetch live flights and stays for candidates"),
         n: int = typer.Option(10, help="Candidate stops (8-12)"),
         no_cache: bool = typer.Option(False, "--no-cache")):
    """Options menu (candidate stops + route combos) for any country/region -> trips/<slug>/menu.md + menu.json."""
    from .menu import run_menu
    cache.configure(enabled=not no_cache)
    cfg = load_brief(brief)
    md, js = run_menu(cfg, brief.resolve().parent, live=live, n=n)
    console.print(f"[green]menu[/green] {md}  {js}")


@app.command()
def suggest(brief: Path = typer.Option(..., "--brief"), live: bool = typer.Option(True, "--live/--no-live"),
            all_: bool = typer.Option(False, "--all", help="Also run plan for every variant")):
    """Menu + route variants (variants.md). With --all, runs plan for each variant into trips/<slug>-vN/."""
    from .menu import run_menu
    cfg = load_brief(brief)
    md, js = run_menu(cfg, brief.resolve().parent, live=live)
    console.print(f"[green]variants[/green] {brief.resolve().parent / 'variants.md'}")
    if all_:
        data = json.loads(Path(js).read_text())
        for i, c in enumerate(data["combos"], 1):
            console.print(f"plan variant {i}: {c['stops_spec']}")
            plan(home=cfg.get("from"), stops=c["stops_spec"], start=data["window"]["start"], trip=f"{brief.resolve().parent.name}-v{i}",
                 brief=brief, alt_start=None, end_airport=None, people=None, budget_night=None, prefs=None,
                 meal_rate=None, party_rate=None, currency=None, passport=None, country=cfg.get("destination"),
                 flights_backend=None, stays_backend=None, browser=None, hostels=False, no_cache=False, png=False)


if __name__ == "__main__":
    app()
