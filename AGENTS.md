# AGENTS.md

Instructions for any AI coding or chat agent working in this repo (Codex, Cursor, Claude Code, Copilot, Kiro, Gemini CLI, Aider).

## What this repo is
`tripforge` is a keyless trip-planning CLI: live nonstop flights (with flight numbers), stays, places, visa/FX/advisory/climate, rendered to a phone-friendly PDF/HTML with an `evidence/` folder. Trips live in `trips/<slug>/`.

## How to behave as the trip planner
Read `agents/PLANNER_PROMPT.md` and follow it. In short: take minimal input, think before fetching, produce an **options menu** first (dates, destination cards, events, priced combos, deltas, decision worksheet), only then a detailed plan; frugal without compromising experience; every price tagged `live` or `est`, never invented; always deliver a PDF; never book or enter credentials.

## How to run the tool
```bash
uv venv && uv pip install -e .            # or: pip install -e .
tripforge plan --from <IATA> --stops "CityA:2,CityB:3,CityC:5" --start 2026-12-24 \
  --people 2 --prefs veg,party --currency <ISO 4217> --trip my-trip
# worked briefs: trips/example-thailand (INR), trips/example-lisbon-morocco (EUR), trips/example-rajasthan-family (domestic, rail, 3 people)
# outputs: trips/my-trip/out/{plan.pdf,plan.html,plan.png,plan.json}, trips/my-trip/evidence/
```
Playwright needs a browser: `playwright install chromium`, or set `--browser headless` to use installed Google Chrome. If Google/Airbnb block the headless browser, use `--browser attach` (see README).

## Building the trip web app (`tripforge site`)
When the user wants a phone-first site for the trip (swipe-able day pages, live weather/FX/flight status, shared ledger behind a
PIN), you do not write HTML. You fill one file and build:
1. `tripforge site init trips/<slug>` writes `trips/<slug>/site/trip.json` from the brief. Read `src/tripforge/site/SCHEMA.md`
   and fill it from the plan and the user's bookings. Compute weekdays from dates; never type them.
2. Research per town with `agents/RESEARCH_BRIEF.md` (one agent per town), then `tripforge site merge-plans trips/<slug>`.
3. Photos: CC-licensed landscapes into `trips/<slug>/site/img/`, credits in `data.cred`. Look at them; reject selfies and crowds.
4. `tripforge site build trips/<slug>` -> `site/dist/`. It refuses JS syntax errors and private data (passport shapes,
   bank details, `private_patterns`). Screenshot at 390px, read the console, look at the pixels.
5. `tripforge site host trips/<slug>` prints the server steps (Caddy block, systemd units, env). The person who owns the host runs them.
The template (`src/tripforge/site/`) is reusable code only: themes, components, lock page, service worker, ledger + PIN API,
flight poller. Anything about a place or a traveller belongs in `trip.json`; `tests/test_site.py` enforces this.

## Conventions
- Follow `docs/FETCH_STRATEGY.md`: define what to fetch and how; never add place names, fares or tips to code or data files.
- Write every trip into `trips/<slug>/` (see `TRIPS.md`); never scatter files elsewhere. Trips are gitignored; commit only sanitised examples.
- One trip = one folder: `brief.yaml` (inputs), `notes.md` (decisions, constraints, open questions), `out/`, `evidence/`.
- Commit trips on a branch and open a PR; `main` is protected.
- Read [docs/DESIGN_PRINCIPLES.md](docs/DESIGN_PRINCIPLES.md) first. No data files under `src/`; fetch strategy, not data. The tool must stay destination- and traveller-agnostic. No currency, home airport, spend rate or country hint may be hardcoded in code or templates (`tests/test_no_bias.py` enforces it). Defaults come from the brief.
- Tests: `pytest -q` (parser fixtures in `tests/fixtures`). Add a fixture when a scraper changes.
- Never add paid API keys as hard requirements. Optional keys are read from env (`SERPAPI_KEY`).
