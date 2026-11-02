# tripforge

Minimal input in, designed trip plan out, for **any destination**. The flow is:

**brief -> menu -> you pick -> plan**

1. Write `trips/<slug>/brief.yaml` (as thin as destination, dates, people, home airport, prefs, rates).
2. `tripforge menu --brief trips/<slug>/brief.yaml` writes `menu.md`: 8-12 candidate stops with vibe fit, suggested nights, stay price per night, how to get there, must-dos with fees, events in your dates, and 3-4 route combos with a core cost each. Every number is tagged live or est.
3. Pick a combo, add `stops:` and `start:` to the brief.
4. `tripforge plan --brief trips/<slug>/brief.yaml` writes `trips/<slug>/out/{plan.pdf,plan.html,plan.png,plan.json}` plus `trips/<slug>/evidence/`.

Nothing is invented. If a fetch fails, the cell says "unavailable".

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
from: BLR
people: 2
prefs: [veg, party]          # also beach, culture, nature, food, or any word
budget_night: 5000           # stay budget per night, INR
meal_rate: 1000              # per meal per person (3 a day)
party_rate: 2500             # per party night per person
stops: "Bangkok:4,Koh Phangan:4,Krabi:2"   # Name:nights[@IATA]
end_airport: HKT             # optional: fly home from a different airport
```

CLI flags (`--from`, `--stops`, `--start`, `--end-airport`, `--prefs`, `--meal-rate`, `--party-rate`, ...) override the brief. `tripforge plan --trip <slug> ...` creates the folder and writes the merged `brief.yaml`, so a re-run needs no flags.

## How it resolves any destination

| Piece | Source (all keyless) |
| --- | --- |
| Stop coordinates, country | Nominatim (1 req/s, cached 30 days) |
| Nearest airports | OurAirports CSV (cached in `cache/`, refreshed monthly); stops without an airport within 40 km get the cheapest of up to 3 nearby airports plus a ground row |
| Flights | `fli` (browserless Google Flights, INR, gl=IN, nonstop, flight numbers); Playwright page fallback when fli is empty twice |
| Stays | `pyairbnb` (bbox, 10+ reviews, 4.6+, sorted by price); Playwright fallback |
| Ground legs | `src/tripforge/data/ground.json` table (Thailand examples), else a distance heuristic (road 60 km/h, ferry 30 km/h, INR/km bands), always labelled indicative |
| Places | Wikivoyage See/Do/Eat/Drink listings (with fees), OSM Overpass for veg food and nightlife when the public instance answers |
| Events | Computed full-moon dates, Wikivoyage and Wikipedia festival mentions in the window |
| Visa, advisory, climate, FX | static table, US State Dept RSS, Sunshine Atlas, frankfurter.app |

`data/places.json` holds curated example entries (areas, highlights, stay centres). They enrich known cities; they are not required.

Cache: `cache/tripforge.db`, TTL flights 8h, stays 24h, places/climate 7d, fx 24h. Every row keeps `fetched_at`; `--no-cache` bypasses it.

## Regression trips

- `trips/thailand-dec26-test/`: `--from BLR --stops "Bangkok:4,Koh Phangan:4,Krabi:2" --start 2026-12-24 --end-airport HKT --prefs veg,party`
- `trips/lisbon-porto-smoke/`: `--from BLR --stops "Lisbon:3,Porto:2" --start 2026-12-24` (no nonstop BLR-LIS exists, so the flight cells read unavailable)
- `trips/thailand-dec26-menu/`: menu example

The `trips/` folder (brief, notes, plan.pdf, plan.json) is committed; GitHub is the source of truth.

## Limitations

- Nonstop flights only; long-haul trips without a nonstop show unavailable flight legs.
- Ground heuristic does not know about trains or water crossings beyond an "island" name/type check.
- Overpass is often slow or down; Wikivoyage fills in.
- Menu vibe fit is a keyword count in the Wikivoyage article, capped per pref.
- Visa table covers a handful of countries for the Indian passport.
