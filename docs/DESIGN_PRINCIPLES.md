# Design principles

**No home country.** Every default derives from the brief or is resolved at runtime. Static data files are optional enrichment, and `src/` ships none (a test enforces it). Every section must justify its presence per trip. Every number is tagged live or est, with a source and a `fetched_at`. The tool never books and never invents.

## Fetch strategy, not data

The repo says WHAT to fetch and HOW. It does not carry answers.

| Need | How it is resolved at runtime |
|---|---|
| Home airport | `from:` or `home_city` in the brief (Nominatim, then OurAirports). No default. |
| Currency | `currency:` in the brief, else the home airport country's currency (Wikidata SPARQL, cached 30 days) |
| Symbols and formats | An ISO 4217 table in code; unknown codes print as the code |
| Daily spend | Only from `meal_rate` / `party_rate` / `transport_day` in the brief; otherwise a placeholder, never a guess |

## Sections

| Section | Shown when | Source | Fallback |
|---|---|---|---|
| Flights | A hop is longer than `max_ground_hours` (default 6) by road | fli (Google Flights, home-country market) | "unavailable" cell with the search link |
| Ground legs | A hop is within `max_ground_hours`, or an airport transfer is needed | OSRM routing for mode and duration; live 12Go read for the fare floor; Wikivoyage "Get in" for a rail note | Duration estimate if OSRM is down; "fare unavailable" plus the 12Go link. A heuristic may give duration, never money |
| Stays | Always | pyairbnb, browser fallback | "unavailable" |
| Stay districts, highlights | The stop has a Wikivoyage article | Wikivoyage Districts, Sleep, See, Do | "No guide article found" |
| Visa | Destination is not the home country and not the passport country | Wikipedia "Visa requirements for ... citizens" via Wikidata ISO codes | Link to the article |
| Safety advisory | Destination is not the home country | By passport: GB FCDO, US State Dept, CA travel.gc.ca; any other passport gets FCDO and US, labelled third-country | Per-source "unavailable" |
| FX | Destination currency differs from the trip currency | frankfurter.app | Omitted when currencies match |
| Climate | Always | Open-Meteo archive, trip month averaged over 5 years; the seasonal warning is computed from the numbers | "unavailable" |
| Forecast | Trip starts within 16 days | Open-Meteo forecast | Note that it is out of range |
| Public holidays | Always, for the home country and each destination | Nager.Date | Row omitted, evidence shows the miss |
| Moon-dated events | Only when a stop's guide text mentions one | Wikivoyage text, dates computed (+/- 1 day) | None |
| Daily spend | The brief gives the rates | The brief | Placeholder asking for the rates |

Sections that do not apply are listed once at the end as "not applicable: <reason>", so the reader knows they were considered.

## Rules for contributors

- No literal currency, airport, country, airline or city in code or templates. `tests/test_no_bias.py` fails the build if one appears.
- No JSON, YAML or CSV data under `src/`. Put sample briefs under `trips/`.
- A new source must say what it is keyed by (passport, country, coordinates), what happens when it is down, and how it is cached.
