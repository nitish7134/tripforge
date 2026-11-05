# tripforge

Minimal input in, designed trip plan out, for **any destination**. The flow is:

**brief -> menu -> you pick -> plan**

1. Write `trips/<slug>/brief.yaml` (as thin as destination, dates, people, home airport, prefs, rates).
2. `tripforge menu --brief trips/<slug>/brief.yaml` writes `menu.md`: 8-12 candidate stops with vibe fit, suggested nights, stay price per night, how to get there, must-dos with fees, events in your dates, and 3-4 route combos with a core cost each. Every number is tagged live or est.
3. Pick a combo, add `stops:` and `start:` to the brief.
4. `tripforge plan --brief trips/<slug>/brief.yaml` writes `trips/<slug>/out/{plan.pdf,plan.html,plan.png,plan.json}` plus `trips/<slug>/evidence/`.

Nothing is invented. If a fetch fails, the cell says "unavailable".

All outputs land in `trips/<slug>/` next to where you run it; `TRIPS.md` explains the layout, privacy and cleanup.

## Install

```bash
uv venv && uv pip install -e . && .venv/bin/tripforge --help
```

`fli` and `pyairbnb` are pinned to git commits in `pyproject.toml` (their PyPI releases predate fixes this tool needs). PDF/PNG rendering uses your installed Chrome through Playwright (`playwright install chromium` as fallback).

## Brief

```yaml
# menu needs destination + start (or month) + nights; plan needs from + stops + start
destination: Thailand        # any country or region with a Wikivoyage article
start: 2026-12-24
nights: 10
from: <IATA>                  # required: your home airport (or home_city: <name>)
currency: <ISO 4217>         # optional: defaults to the home airport country's currency
people: 2
prefs: [veg, party]          # also beach, culture, nature, food, or any word
budget_night: <amount>       # optional stay cap per night, in the trip currency (omit for no cap)
meal_rate: <amount>          # per meal per person (3 a day); required for the daily spend section
party_rate: <amount>         # per party night per person; required for party trips
stops: "Bangkok:4,Koh Phangan:4,Krabi:2"   # Name[/Stay area]:nights[@IATA]; "Krabi/Ao Nang:2" pins stays to walking distance of that area
end_airport: HKT             # optional: fly home from a different airport
stays:
  hostelworld:               # optional: Hostelworld property ids per stop (the number in the property URL); live dorm/private prices
    Krabi: [322541]
```

CLI flags (`--from`, `--stops`, `--start`, `--end-airport`, `--prefs`, `--meal-rate`, `--party-rate`, ...) override the brief. `tripforge plan --trip <slug> ...` creates the folder and writes the merged `brief.yaml`, so a re-run needs no flags.

**Defaults come from your brief; the tool has no home country.** Currency falls back to the home airport's country (Wikidata), money is formatted from an ISO 4217 table, and daily spend is only shown when you give `meal_rate` / `party_rate`. Country-specific hints (visa rules, advisories) come from fetched sources, never from the code.

## Domestic family trip (rail-friendly)

```yaml
# trips/example-rajasthan-family/brief.yaml (sanitised): family of 3, January, round trip from a mid-country city
destination: Rajasthan, India     # "Region, Country" is fine; resolved to a Wikivoyage article
from: NAG
people: 3
pace: relaxed                     # 2 sights a day, no party/nightlife section unless prefs ask for it
ground: {rail_ok: true, night_travel_ok: true, rail_max_hours: 26}
flights: {max_total_hours_if_stop: 12}   # one-stop fallback when no nonstop exists
stays: {guests: 3}                # entire place sized for the party; cost still split over `people`
stops: "Jaipur:2,Jodhpur:2,Jaisalmer:2,Udaipur:2"
```

`tripforge menu --brief trips/example-rajasthan-family/brief.yaml` lists the region's candidate stops; `tripforge plan --brief ...` prices flights, shows a **rail row and a road row beside each flight row** (every rail and road row is tagged indicative; a rail fare is shown only if a page states it, otherwise "fare unavailable"), and says which option the totals use. India has a working rail adapter; other countries show the rail row as unavailable until an adapter is added in `fetchers/rail.py`.

## Fetch strategy, not data

tripforge ships no travel data. `docs/FETCH_STRATEGY.md` lists every piece of information a plan needs, which source answers it for the trip in hand, the fallback, and how it is tagged. Heuristics may estimate time, never money.

## How it resolves any destination

| Piece | Source (all keyless) |
| --- | --- |
| Stop coordinates, country | Nominatim (1 req/s, cached 30 days) |
| Nearest airports | OurAirports CSV (cached in `cache/`, refreshed monthly); stops without an airport within 40 km get the cheapest of up to 3 nearby airports plus a ground row |
| Flights | `fli` (browserless Google Flights in your trip currency and home-country market, nonstop, flight numbers); Playwright page fallback when fli is empty twice |
| Stays | `pyairbnb` (bbox, 10+ reviews, 4.6+, sorted by price); Playwright fallback |
| Rail | per-country adapter (India: erail.in timetable, station codes from Wikipedia infoboxes) and the stop's Wikivoyage "By train" text; honours `ground.night_travel_ok`, `ground.rail_max_hours` and `pace`; indicative, no fares invented |
| Ground legs | OSRM routing for mode and duration, a live 12Go read for the fare floor (else "fare unavailable" plus the link), Wikivoyage "Get in" for a rail note. A heuristic may give duration, never money |
| Places | Wikivoyage See/Do/Eat/Drink listings (with fees), OSM Overpass for veg food and nightlife when the public instance answers |
| Events | Public holidays for the home country and each destination (Nager.Date), Wikivoyage and Wikipedia festival mentions; moon-dated events only when a stop's guide mentions one |
| Visa | Wikipedia "Visa requirements for <Demonym> citizens" (live via the MediaWiki API, passport and destination resolved from Wikidata ISO codes; cached 30 days; shows status, stay, revision date, source link). Skipped for domestic trips and for the passport's own country. Passport defaults to the home airport's country (`--passport` / `passport:` override) |
| Advisory | By passport: GB FCDO, US State Dept, CA travel.gc.ca; other passports get FCDO + US labelled third-country |
| Climate | Open-Meteo archive normals for any lat/lon (trip month, 5-year average) with a computed seasonal warning |
| FX | frankfurter.app, only when the destination currency differs |

Stay districts, highlights and the stay centre come from each stop's Wikivoyage article (Districts, Sleep, See, Do). No curated data ships in `src/`.

## Fetch strategy, not data

The repo defines WHAT to fetch and HOW, never the answers: no per-pair fares, no curated cities, no currency or airport defaults. See [docs/DESIGN_PRINCIPLES.md](docs/DESIGN_PRINCIPLES.md) for the section-by-section table (when shown, source, fallback).

Cache: `cache/tripforge.db`, TTL flights 8h, stays 24h, places/climate 7d, fx 24h. Every row keeps `fetched_at`; `--no-cache` bypasses it.

## Regression trips

- example (sanitised, Thailand from India, brief sets `currency: INR`): `--from BLR --stops "Bangkok:4,Koh Phangan:4,Krabi:2" --start 2026-12-24 --end-airport HKT --prefs veg,party`
- second example (Europe to Morocco, EUR resolved from the home airport): `trips/example-lisbon-morocco/brief.yaml`
- smoke: `--from BLR --stops "Lisbon:3,Porto:2" --start 2026-12-24 --currency INR` (no nonstop BLR-LIS exists, so the flight cells read unavailable)

Your own trips are personal: `trips/` is gitignored except `trips/example-thailand/` and `trips/README.md`. Keep real trips in a private location (or a private fork) and commit only sanitised examples here.

## Limitations

- Nonstop flights only; long-haul trips without a nonstop show unavailable flight legs.
- Flights are nonstop unless the brief sets `flights.max_total_hours_if_stop`, which adds a one-stop fallback for legs with no nonstop; hops short enough for road or ferry become ground legs.
- Rail: one working adapter (India); fares are never estimated; only direct trains are read (no connection search).
- Ground fares come from a live 12Go read, which often returns nothing to a plain HTTP client; the plan then says "fare unavailable" and links the page. Rail is a note only.
- AU and other passports without an integrated advisory source get the UK and US advisories, labelled third-country.
- Overpass is often slow or down; Wikivoyage fills in.
- Menu vibe fit is a keyword count in the Wikivoyage article, capped per pref.
- Visa data is community-maintained Wikipedia text; the plan always says to verify with the embassy. If Wikipedia cannot be read the cell says unavailable and links the article.
- Scrapes page text for the browser fallbacks; Google/Airbnb layout changes can break those parsers (`tests/` has fixtures).

## Trip page (during the trip)

Once the trip is booked, `tripforge site` turns it into an offline phone page: day-by-day swipe deck, currency
calculator, shared ledger with minimal settle-up, driver cards, PIN-gated with member and visitor roles.

```bash
tripforge site init trips/my-trip/site --brief trips/my-trip/brief.yaml   # uses out/plan.json when present; unknowns are TODOs
tripforge site build trips/my-trip/site                                    # src/ -> index.html (node --check)
tripforge site check trips/my-trip/site                                    # stale build or brief.private_patterns hit -> exit 1
```

Template, field reference and deploy recipe: [site_template/README.md](site_template/README.md). What went wrong last
time and how to avoid it: [docs/LEARNINGS.md](docs/LEARNINGS.md).

## Trips folder and the planner agent

See `TRIPS.md` for exactly where files are written and how to delete them.

Each trip lives in `trips/<slug>/`: `brief.yaml` (inputs, however few), `notes.md` (decisions, friend constraints, open questions), `out/` (menu/plan PDF + HTML + PNG) and `evidence/` (every search screenshot). Example: `trips/example-thailand/` (sanitised sample).

`agents/tripforge-planner.json` is a Kiro agent spec for a destination-agnostic trip planner: minimal input in, options menu out (dates with live fares, destination cards with fees and inclusions, events, priced combos, decision worksheet), then a detailed plan once you pick. Install with `cp agents/tripforge-planner.json ~/.kiro/agents/` and start a session with that agent. The agent never books anything; it gives links.

## Use it with your own AI agent (Claude, ChatGPT, Copilot, Cursor, Codex, Kiro)

tripforge is a CLI plus a prompt. Any agent that can run shell commands can drive it; any chat model can at least plan with the prompt. Three pieces:

| File | Purpose |
|---|---|
| `agents/PLANNER_PROMPT.md` | The planner behaviour as plain text. Paste it into any agent's system prompt / custom instructions. |
| `AGENTS.md` | Repo conventions for coding agents (Codex, Cursor, Aider, Gemini CLI read this automatically). |
| `agents/tripforge-planner.json` | Ready-made Kiro / Kiro Crew agent spec. |

### Claude Code
`CLAUDE.md` in the repo root already points at `AGENTS.md` and the prompt, so `claude` picks it up when started in this folder. Ask: *"Plan a 10-night Thailand trip from BLR around 24 Dec for 2 people, veg, party-friendly, ₹5k/night."* It will write `trips/<slug>/brief.yaml`, run `tripforge plan`, and hand you `trips/<slug>/out/plan.pdf`.

### Claude Desktop / Claude.ai Projects
Create a Project, paste `agents/PLANNER_PROMPT.md` into the project instructions, attach a trip's `out/plan.json` or `notes.md` when you want it to reason over results. Claude Desktop cannot run the CLI itself; run `tripforge plan` locally and upload the outputs, or connect a shell MCP server.

### ChatGPT (custom GPT or a Project)
Paste `agents/PLANNER_PROMPT.md` as the GPT's instructions. ChatGPT cannot execute `tripforge`, so use it for the options-menu reasoning and give it live numbers by uploading `plan.json` / the PDFs from `trips/<slug>/out/`. With Code Interpreter on it can read `plan.json` and recompute budgets with your own rates.

### GitHub Copilot (VS Code / Copilot Chat)
`.github/copilot-instructions.md` is already in the repo. Open the folder in VS Code, and Copilot Chat follows it. Agent mode can run `tripforge plan` in the terminal when you ask.

### Cursor / Windsurf / Codex CLI / Gemini CLI / Aider
All of these read `AGENTS.md` (Cursor also accepts it as a rule file). Open the repo and ask for a plan; they run the CLI and write to `trips/<slug>/`.

### Kiro / Kiro Crew
`cp agents/tripforge-planner.json ~/.kiro/agents/` and start a session with the `tripforge-planner` agent. The Kiro Crew skill lives at `~/.kiro/crew/skills/tripforge/SKILL.md`.

### No agent at all
```bash
uvx --from git+https://github.com/nitish7134/tripforge tripforge plan \
  --from BLR --stops "Bangkok:4,Koh Phangan:4,Krabi:2" --start 2026-12-24 \
  --people 2 --budget-night 5000 --prefs veg,party --trip thailand
open trips/thailand/out/plan.pdf
```

### Giving the agent your constraints
Put them in `trips/<slug>/brief.yaml` (see `trips/example-thailand/brief.yaml` for a full example: dates and alternatives, people, nonstop-only, stay budget, hostels OK, veg, per-meal and per-party-night rates, optional destination cards, must-consider questions). Any agent can read that file and the matching `notes.md`, so a plan started in one tool can be continued in another.

### What agents must not do
Book, pay, enter credentials, or invent prices. The prompt says so; keep it when you adapt it.
