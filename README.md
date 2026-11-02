# tripforge

Minimal input in, designed trip plan out. `tripforge plan` reads live nonstop flights (with flight numbers and times) from Google Flights and stays from Airbnb, adds visa, FX, travel advisory, climate and photos, and writes a self-contained `plan.html`, a `plan.png`, a `plan.json` and an `evidence/` folder.

Nothing is invented. If a fetch fails, the plan says "unavailable" for that cell.

## Install and run

```bash
uvx --from git+https://github.com/nitish7134/tripforge tripforge plan \
  --from BLR --stops "Phuket:2,Krabi:3,Bangkok:5" --start 2026-12-24 \
  --people 2 --budget-night 5000 --prefs veg,party --currency INR
```

(The repo is private, so use a machine where `gh auth login` / git credentials work.)

Local dev: `uv venv && uv pip install -e . && .venv/bin/tripforge --help`.

Browser: headless mode drives your installed Google Chrome through Playwright (no browser download). Playwright's own Chromium is the fallback (`playwright install chromium`).

## Options

| Option | Meaning |
| --- | --- |
| `--from` | Home airport IATA (BLR, DEL, BOM, ...) |
| `--stops` | `City:nights` list, optional `@IATA` override |
| `--start` | Arrival date at first stop; `--alt-start` (repeatable) adds more options to compare |
| `--people`, `--budget-night`, `--currency`, `--passport` | Group size, nightly stay budget, price currency, visa table passport |
| `--prefs` | Free tags such as `veg,party` (shown in the plan header) |
| `--hostels` | Also search cheap private rooms per stop |
| `--browser headless\|attach` | See below |
| `--out` | Output directory (default `out/`) |

`tripforge render out/plan.json --png` re-renders without refetching.

## Attach mode (your real Chrome)

Google or Airbnb may block headless browsers on some networks. `--browser attach` drives your logged-in Chrome through [playwright-cli](https://github.com/microsoft/playwright-cli) and its Chrome extension relay:

1. Install the Playwright Chrome extension, make sure `playwright-cli` is on PATH (or set `TRIPFORGE_PWCLI`), and Node 24+ is available (`TRIPFORGE_NODE_BIN` defaults to `/opt/homebrew/opt/node@24/bin`).
2. Run with `--browser attach`. tripforge uses session slug `tripforge` (`TRIPFORGE_SLUG` to change), opens its own tab and closes it afterwards.
3. Approve the connection in Chrome when prompted. The relay can drop; just rerun.

## Data sources (all keyless)

Google Flights page, Airbnb search page, frankfurter.app (FX), travel.state.gov RSS (US advisory), sunshineatlas.com MCP (climate normals), open-meteo (forecast, only within 16 days), Wikimedia Commons (photos, attribution kept). Visa info is a static, hand-maintained table in `src/tripforge/data/visa.json` with source links and a verify line. Daily spend ranges are labelled estimates.

## Limitations

- Scrapes page text; Google/Airbnb layout changes will break parsers. `tests/` has parser fixtures.
- Nonstop flights only. Stops without their own airport (for example Railay) are not modelled.
- Destinations come from `src/tripforge/data/places.json`; add cities there.
- Visa table covers a handful of countries for the Indian passport only.
- Day plans use curated highlights per destination, not live events.

## Trips folder and the planner agent

Each trip lives in `trips/<slug>/`: `brief.yaml` (inputs, however few), `notes.md` (decisions, friend constraints, open questions), `out/` (menu/plan PDF + HTML + PNG) and `evidence/` (every search screenshot). Example: `trips/thailand-dec26/`.

`agents/tripforge-planner.json` is a Kiro agent spec for a destination-agnostic trip planner: minimal input in, options menu out (dates with live fares, destination cards with fees and inclusions, events, priced combos, decision worksheet), then a detailed plan once you pick. Install with `cp agents/tripforge-planner.json ~/.kiro/agents/` and start a session with that agent. The agent never books anything; it gives links.
