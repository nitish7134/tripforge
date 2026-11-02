"""tripforge CLI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from .plan import PlanError, run_plan
from .render import render as do_render

app = typer.Typer(add_completion=False, help="Minimal-input trip planner: live flights, stays, visa/FX/advisory/climate -> HTML + PNG.")
console = Console()


@app.command()
def plan(
    home: str = typer.Option(..., "--from", help="Home airport IATA, e.g. BLR"),
    stops: str = typer.Option(..., help='Comma list "City:nights", e.g. "Phuket:2,Krabi:3,Bangkok:5"'),
    start: str = typer.Option(..., help="Start date YYYY-MM-DD (arrival at first stop)"),
    alt_start: Optional[List[str]] = typer.Option(None, "--alt-start", help="Extra start date(s) to compare (repeatable)"),
    people: int = typer.Option(2, help="Travellers"),
    budget_night: int = typer.Option(5000, "--budget-night", help="Stay budget per night, in --currency"),
    prefs: str = typer.Option("", help="Comma list, e.g. veg,party"),
    currency: str = typer.Option("INR", help="Currency for prices"),
    passport: str = typer.Option("IN", help="Passport country code for visa table"),
    out: Path = typer.Option(Path("out"), help="Output directory"),
    browser: str = typer.Option("headless", help="headless (system Chrome) or attach (your logged-in Chrome via playwright-cli)"),
    hostels: bool = typer.Option(False, "--hostels", help="Also search cheap private rooms"),
    png: bool = typer.Option(True, "--png/--no-png", help="Also render plan.png"),
):
    """Build out/plan.json, plan.html, plan.png and out/evidence/."""
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        p = run_plan(home=home, stops_spec=stops, starts=[start, *(alt_start or [])], people=people,
                     budget_night=budget_night, prefs=[x.strip() for x in prefs.split(",") if x.strip()],
                     currency=currency.upper(), passport=passport.upper(), out=out,
                     browser_mode=browser, hostels=hostels)
    except PlanError as e:
        console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(2)
    pj = out / "plan.json"
    pj.write_text(json.dumps(p, indent=1, ensure_ascii=False))
    html, pngp = do_render(pj, png=png)
    console.print(f"[green]done[/green] {html}" + (f"  {pngp}" if pngp else ""))
    for o in p["options"]:
        console.print(f"[bold]Option {o['start']}[/bold] core/person: {o['totals']['core_pp']}  (missing legs {o['totals']['flight_legs_missing']}, stays {o['totals']['stays_missing']})")
        for lg in o["legs"]:
            if lg["rows"]:
                r = lg["rows"][0]
                console.print(f"  {lg['date']} {r['flight']:8} {r['from']} {r['dep']} -> {r['to']} {r['arr']}  {r['price']}")
            elif lg["kind"] == "ground":
                console.print(f"  {lg['date']} {lg['orig']}->{lg['dest']} by road/ferry (not searched)")
            else:
                console.print(f"  {lg['date']} {lg['orig']}->{lg['dest']} unavailable")


@app.command()
def render(plan_json: Path = typer.Argument(Path("out/plan.json")), png: bool = typer.Option(False, "--png", help="Also write plan.png")):
    """Re-render plan.html (and PNG) from an existing plan.json without refetching."""
    html, pngp = do_render(plan_json.resolve(), png=png)
    console.print(f"[green]rendered[/green] {html}" + (f"  {pngp}" if pngp else ""))


if __name__ == "__main__":
    app()
