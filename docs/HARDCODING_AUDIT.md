# tripforge hardcoding audit

Repo: `/Users/hinitish/.kiro/crew/workspace/tripforge` at `a76b72b` (main, PR #16 merged). Read-only audit, no code changed.
Paths below are relative to the repo root; `src/` means `src/tripforge/`.

## Baseline: what is already clean

`src/` ships no place, fare, currency or airport tables (`tests/test_no_bias.py:63-87` enforces it). Currency resolves from the home airport via Wikidata (`money.py:52-66`), passport defaults to the home country (`plan.py:382`), visa is read live from Wikipedia (`fetchers/visa.py`), stays/flights/hostels are live, places come from Wikivoyage + Overpass, climate from Open-Meteo. So the remaining hardcoding is mostly: region-locked sources, money heuristics in `menu`, tuning constants that are not overridable, stale endpoints/docs, and brief-schema drift.

Live checks made during the audit (2026-11-05):

| Probe | Result |
|---|---|
| `GET https://api.frankfurter.app/latest?from=THB&to=INR` | 301 -> `https://api.frankfurter.dev/v1/latest?from=THB&to=INR`, 200 |
| `GET https://api.frankfurter.dev/v1/latest?base=THB&symbols=INR` | 200, `{"date":"2026-11-04","rates":{"INR":2.8133}}` |
| `POST/GET https://sunshineatlas.com/api/mcp` | 406 |
| `GET https://12go.asia/en/travel/bangkok/krabi` | 202 (bot wall, no fare in body) |
| `GET prod.apigee.hostelworld.com/legacy-hwapi-service/2.2/suggestions/?text=Krabi` | 200, keyless, returns city id `1124` + country |
| `GET .../2.2/cities/1124/properties/` | `Invalid Credentials` (listing needs a key) |
| `GET https://www.hostelworld.com/st/hostels/asia/thailand/krabi/` (follow redirect) | 200, HTML contains `hostels/p/<id>` links (8+ ids) |
| `GET .../2.2/properties/322541/` | 200, keyless (already used by `fetchers/hostels.py`) |

## Fetchers that exist in the repo (reuse these first)

| Module | Source | Call shape | Cache key / TTL (`cache.py:20-21`) |
|---|---|---|---|
| `fetchers/airports.py` | OurAirports CSV | `by_iata(code)`, `nearest(lat, lon, k)`, `resolve_home(cfg)`, `countries()` | file mtime 30 d |
| `fetchers/geo.py` | Nominatim | `geocode(q)`, `geocode_point(q)`, `stay_bbox(...)` | `geo` 30 d |
| `fetchers/destination.py` | Wikivoyage API | `resolve(text)` | `places` 7 d |
| `fetchers/places.py` | Overpass + Wikivoyage | `wikivoyage(page)`, `guide(name)`, `stop_places(stop, diets)`, `overpass(lat, lon, r, diets)` | `places` 7 d |
| `fetchers/flights_fli.py` | Google Flights via fli | `fetch_leg(o, d, date, ccy, gl)`, `fetch_leg_one_stop(..., max_h)` | `flights` 8 h |
| `fetchers/flights.py` | Google Flights via Playwright | `fetch_leg(br, o, d, date, ccy, evid)` | `flights` 8 h |
| `fetchers/stays_pyairbnb.py` | Airbnb via pyairbnb | `fetch_stay(bbox, slug, cin, cout, nights, adults, budget, ccy, room_type)` | `stays` 24 h |
| `fetchers/stays.py` | Airbnb via Playwright | `fetch_stay(br, slug, ...)` | `stays` 24 h |
| `fetchers/hostels.py` | Hostelworld legacy API 2.2 | `fetch_hostel(pid, cin, nights, guests, ccy)` -> `/properties/{id}/` + `/properties/{id}/availability/?date-start&num-nights&guests&currency` | `hostels` 12 h |
| `fetchers/rail.py` | erail.in + Wikipedia + Wikivoyage | `quote(a, b, cc, date, max_h, night_ok)`, `by_train_note(name)` | `ground` 7 d |
| `ground.py` | OSRM + 12Go | `route(a, b)`, `fare(a_name, b_name, ccy)`, `estimate(a, b, ccy)` | `ground` 7 d |
| `fetchers/climate.py` | Open-Meteo archive | `fetch_normals(lat, lon, month)` | `climate` 7 d |
| `fetchers/misc.py` | Frankfurter, Open-Meteo forecast | `fetch_fx(src, dst, evid)`, `fetch_weather(lat, lon, start, end, evid, tag)` | `fx` 24 h / none |
| `money.py` | Wikidata SPARQL, Frankfurter | `country_currency(cc)`, `rate(src, dst)`, `resolve_currency(cfg, home_cc)` | `geo` 30 d, `fx` 24 h |
| `fetchers/advisory.py` | FCDO, US State Dept RSS, Canada | `fetch_advisories(passport, {cc: name}, evid)` | none |
| `fetchers/visa.py` | Wikipedia + Wikidata | `visa_requirement(passport, dest)` | `visa` 30 d |
| `fetchers/photos.py` | Wikimedia Commons | `fetch_photos(query, n, dir)` | disk |
| `events.py` | Nager.Date, Wikipedia, Wikivoyage, computed lunar | `public_holidays(cc, s, e)`, `wikipedia_festivals(...)`, `section_mentions(...)`, `lunar_rows(...)` | `holidays` 30 d |

Not in the repo: adsb.lol, AeroDataBox. Neither is needed for pricing; AeroDataBox (RapidAPI key) would only serve route-existence checks (`GET https://aerodatabox.p.rapidapi.com/airports/iata/{IATA}/stats/routes/daily`), adsb.lol only live positions. Do not add them for this audit's gaps.

---

## (A) Wrong for any trip that is not a Thailand/India trip, or wrong for every trip

| # | file:line | Literal | Why it is wrong | Replacement (tool, call shape, cache) |
|---|---|---|---|---|
| A1 | `src/ground.py:20` | `GO12 = "https://12go.asia/en/travel/{a}/{b}"` | 12Go only covers Asia (+ a few EU routes); every Europe/Americas/Africa ground fare is "unavailable" by construction. Live probe returns 202 bot wall even in Asia | Fare-source registry keyed by the hop's country, like `rail.ADAPTERS`: `{"asia-default": 12go, "EU": flixbus, ...}`. FlixBus: `GET https://global.api.flixbus.com/search/autocomplete/cities?q=<name>&lang=en` -> city id, then `GET https://global.api.flixbus.com/search/service/v4/search?from_city_id=..&to_city_id=..&departure_date=DD.MM.YYYY&products={"adult":N}&currency=<CCY>` (unverified, test before adopting). Unknown country -> fare None + link. Cache `ground` 24 h (fares), not 7 d |
| A2 | `src/templates/plan.html.j2:92` | anchor text `12Go` | Labels every ground link "12Go" even where the source is something else | Render `g.fare_source` (name of the adapter that produced `fare_url`) |
| A3 | `src/fetchers/rail.py:23,120` | `ERAIL = "https://erail.in/..."`, `ADAPTERS = {"IN": erail}` | Rail rows exist only for India; every other country returns "no rail-quote adapter" | Default adapter for all countries: Transitous/MOTIS (GTFS, keyless) `GET https://api.transitous.org/api/v5/plan?fromPlace=<lat>,<lon>&toPlace=<lat>,<lon>&time=<ISO>&transitModes=RAIL,REGIONAL_RAIL,LONG_DISTANCE` (unverified) for times; per-country fare adapters where a keyless one exists (DE: `GET https://v6.db.transport.rest/journeys?from=<id>&to=<id>&departure=<ISO>`; TH/VN/KH: 12Go train pages). Keep `IN: erail`. Cache `ground` 7 d timetable, 24 h fares |
| A4 | `src/fetchers/rail.py:46,56` | `"{city} railway station code"`, infobox regex `code=` | Station-code lookup follows Indian Wikipedia infobox convention; other networks use UIC/EVA ids or none | Move into the erail adapter; Transitous/db-rest resolve stations from coordinates (`/geocode?text=` / `/locations?query=`) |
| A5 | `src/menu.py:24` | `VIBE["party"] = r"...|full moon|..."` | "full moon" is a Koh Phangan-specific party cue baked into the generic vibe score; inflates Thai islands, means nothing elsewhere | Score party fit from the article itself: count of Wikivoyage `drink` listings (`wikivoyage(page).data["items"]` kind=="drink") + OSM `amenity=nightclub/bar` count from `overpass(...)`; drop phrase lists. Keep a pref word -> `re.escape(pref)` fallback |
| A6 | `src/menu.py:79,158` | `"full_moon_text": "full moon" in text.lower()`, `lunar_rows(..., ["full moon"] ...)` | Special-cases full moon; new-moon/other lunar festivals ignored; Thailand-flavoured | Pass the candidates' raw article texts to `events.lunar_rows(start, end, [c_text...])`, which already detects `(full|new) moon` generically (`events.py:168-180`). Also compute new-moon dates (currently `[]` at `events.py:175`) |
| A7 | `src/menu.py:101` | `g += min(near) / 3  # domestic hop ~ a third of the long-haul fare` | Money from a heuristic, violating `docs/FETCH_STRATEGY.md:46` rule 2; wrong for every trip | Per hop: `ground.needs_ground` false -> `FL.fetch_leg(a["iata"], b["iata"], hop_date, ccy, home_cc)` via `cache.cached("flights:fli", ...)` exactly like `plan.fetch_flight`; missing -> `None`, mark combo "partial" |
| A8 | `src/menu.py:94-96` | return fare assumed = outbound fare to the last stop | Money from a heuristic; outbound and return prices are routinely 2x apart | `FL.fetch_leg(order[-1]["iata"], home, end.isoformat(), ccy, home_cc)` (one query per distinct last-stop airport) |
| A9 | `src/menu.py:140-156` | `statistics.median(known)` used as stay price for candidates 7-10 | Price estimate shown as a number; not a read | Fetch all `n` candidates (pyairbnb is cached 24 h), or render `unavailable` for the rest. If kept, it must not enter `core_pp` |
| A10 | `src/plan.py:440-442`, `trips/*/brief.yaml stays.hostelworld` | Hostelworld property ids typed by hand per stop (e.g. `Krabi: [322541, 316736]`) | Any new trip without hand-pasted ids gets zero hostel rows; ids are trip facts copied from a browser | New `fetchers/hostels.py: discover(stop)`: (1) `GET prod.apigee.hostelworld.com/legacy-hwapi-service/2.2/suggestions/?text=<stop name>` -> `city.id`, `city.name`, `city.country` (verified keyless); (2) `GET https://www.hostelworld.com/st/hostels/<continent>/<country-slug>/<city-slug>/` (follow redirect; continent from Wikidata `P30` of the country ISO2) -> regex `hostels/p/(\d+)`; (3) existing `fetch_hostel(pid, ...)` for the top K. Cache ids in `hostels:discover` 30 d. Brief `stays.hostelworld` stays as an override. The `cities/{id}/properties/` listing needs credentials (verified), do not use it |
| A11 | `src/stops.py:30` | `airbnb = f"{name}--{country}"` slug | Airbnb's location slug format is guessed; used only by the browser fallback and the evidence URL | Keep, but prefer `stay_bbox(...)` -> pyairbnb (already primary). Low impact |

## (B) Goes stale within weeks or months (endpoints, versions, docs, dated examples)

| # | file:line | Literal | Why it is wrong | Replacement |
|---|---|---|---|---|
| B1 | `src/money.py:14` | `FRANKFURTER = "https://api.frankfurter.app/latest"` | Domain now 301-redirects to `api.frankfurter.dev/v1` (verified); redirect can be dropped any time | `https://api.frankfurter.dev/v1/latest?base=<SRC>&symbols=<DST>` -> `rates[DST]`; cache `fx` 24 h (rate dated by `date` field) |
| B2 | `src/fetchers/misc.py:15` | `url = f"https://api.frankfurter.app/latest?from={src}&to={dst}"` | Same stale domain, duplicated FX code path | Call `money.rate(src, dst)` and keep `fetch_fx` only for writing the evidence JSON |
| B3 | `src/fetchers/misc.py:51-72` | `fetch_climate` -> `https://sunshineatlas.com/api/mcp` | Dead code (unused), endpoint returns 406 | Delete; `fetchers/climate.py:fetch_normals` (Open-Meteo archive) already replaces it |
| B4 | `src/fetchers/misc.py:27-48` | legacy `fetch_advisories` (US-only RSS) | Dead duplicate of `fetchers/advisory.py`; risks re-import of US-default behaviour | Delete |
| B5 | `src/browser.py:11-12` | UA `Chrome/130.0.0.0` | Frozen browser version; stale UAs get bot-walled | Omit the UA override (Playwright sends the real Chrome UA) or read `browser.version` at launch |
| B6 | `src/fetchers/common.py:9` | `tripforge/0.1` in User-Agent | `pyproject.toml:7` is 0.2.0; drifts every release | `importlib.metadata.version("tripforge")` |
| B7 | `pyproject.toml:13-16` | fli `@881aee5`, pyairbnb `@1ee4151` | Airbnb rotates its persisted-query hash and Google changes page format; pinned commits silently return empty | Keep pins, add a weekly canary (`pytest -m live` doing one `fetch_leg` + one `fetch_stay` on a far-future date) that fails loudly |
| B8 | `src/fetchers/stays_pyairbnb.py:93-98` | positional `search.get(key, cursor, ..., 13, ccy, room_type, 0, price_max, [], False, adults, 0,0,0, ceil(adults/2), 0, "en", "", "")` | Positional contract of a fragile scraper; zoom `13` and arg order break on upgrade | Keyword arguments; read zoom from bbox size |
| B9 | `src/fetchers/rail.py:105` | UA override `"Mozilla/5.0"` for erail | Bot-evasion string that will stop working | Use `HEADERS`; if blocked, return `fail` with URL (already the contract) |
| B10 | `agents/PLANNER_PROMPT.md:24` (and `agents/tripforge-planner.json` prompt) | `frankfurter.app (FX), travel.state.gov RSS (advisory), sunshineatlas.com MCP (climate)` | Contradicts code: advisory is passport-keyed (`fetchers/advisory.py`), climate is Open-Meteo, sunshineatlas is dead | Point to `docs/FETCH_STRATEGY.md` only, or list: Frankfurter `api.frankfurter.dev/v1`, passport-keyed advisories, Open-Meteo archive/forecast |
| B11 | `agents/PLANNER_PROMPT.md:22` | `filter >=10 reviews and >=4.6` | Duplicates code thresholds (C9) in prose; drifts | "use the brief's `stays.min_reviews` / `stays.min_rating`" |
| B12 | `docs/FETCH_STRATEGY.md:33` | `(UK, US, AU, CA known)` | Code has GB/US/CA only (`fetchers/advisory.py:24`); `tests/test_no_bias.py:93` asserts AU absent | Fix doc, or add AU (see C30) |
| B13 | `README.md:28-43, 96-98, 152-154`; `AGENTS.md:15-16` | `destination: Thailand`, `--from BLR`, `--start 2026-12-24`, `--budget-night 5000`, `Krabi: [322541]`, `end_airport: HKT` | Example dates fall into the past after Dec 2026; example still teaches the Thailand/INR trip as the canonical brief, and a Hostelworld id that will churn | Use the Lisbon->Morocco example as the README default, write dates as `<YYYY-MM-DD>` or "a date 2+ months out", drop the hostel id example (discovery, A10) |
| B14 | `trips/example-thailand/brief.yaml:7-8`, `trips/example-rajasthan-family/brief.yaml:8`, `trips/example-lisbon-morocco/brief.yaml:7` | `start: 2026-12-24`, `2027-01-10`, `2027-03-13` | Regression briefs stop being runnable once the dates pass (flights return nothing) | `start: +60d` relative syntax resolved by `cli.load_brief` (e.g. `start: "+60d"` -> today+60), or regenerate dates in a test fixture |
| B15 | `tests/fixtures/airbnb_cards.txt`, `hostelworld_availability.json` (`3640.10 INR`), `flights_raw.txt` (`24238` BLR-HKT), `visa_wikitext_*.txt` | captured prices/rules | Fine as parser fixtures; NOT a data source. Note only | Keep; ensure no code path reads `tests/fixtures` |

## (C) Reasonable defaults that must be overridable from brief.yaml (or derived)

| # | file:line | Literal | Why | Replacement (brief key / derivation) |
|---|---|---|---|---|
| C1 | `src/plan.py:36`, `src/menu.py:120`, `src/cli.py:53` | `people: 2` default | Traveller count is user input, never a default; two-person default silently prices for 2 | Required key `people`; missing -> ask (planner) or `PlanError` |
| C2 | `src/plan.py:37`, `src/menu.py:197` | `meals_per_day: 3`; menu hardcodes `days * 3 * meal` | Menu ignores the brief's `meals_per_day` | `spend.meals_per_day` (default 3), used by both `plan.daily_spend` and `menu` |
| C3 | `src/plan.py:37`, `src/menu.py:197`, `src/plan.py:309` | `party_share: 0.5`; menu `nights // 2`; day plan `k % 2 == 0` | Three different "party every other night" rules; only `plan` reads the brief | `spend.party_nights` (explicit count or per-stop map) or `spend.party_share`; derive day-plan nights from the same number |
| C4 | `src/plan.py:38,397` | `max_ground_hours: 6` passed as `float(cfg["max_ground_hours"]) * 60` into `transitions(max_km=...)` | Unit bug: 6 hours becomes 360 **km** of straight-line*1.25 road distance; real drive time never consulted. Overrides `GROUND_MAX_KM=350` by coincidence | Decide ground vs fly after `ground.route(a, b)`: `duration_h <= ground.max_hours` (brief), else fly. Keep km only as pre-filter |
| C5 | `src/ground.py:28` | `GROUND_MAX_KM = 350` | Pre-filter distance; region-dependent (fast rail in EU/JP) | `ground.max_km` in brief, default 350 |
| C6 | `src/ground.py:22-26,123-144` | `FERRY_KMH=30`, `ROAD_FACTOR=1.25`, `ROAD_KMH_FALLBACK=60`, `SNAP_MAX_M=3000`, `INDIRECT_RATIO=4.0`, `+0.3`/`+0.5` h buffers, `x0.9`/`x1.3` band | Duration heuristics (allowed: time, not money). Ferry speed varies 15-60 km/h | Ferry duration: read from the 12Go/aggregator page when present; else keep constants, expose `ground.ferry_kmh`. Others stay internal |
| C7 | `src/plan.py:205` | `RAIL_MAX_HOURS = 18` | Already overridable (`ground.rail_max_hours`) | none (OK) |
| C8 | `src/plan.py:206-207` | `PACE_SIGHTS = {relaxed:2, balanced:3, packed:4}`, `EARLY_MIN = 08:00` | Personal tempo | `pace.sights_per_day`, `pace.earliest_departure: "08:00"` |
| C9 | `src/fetchers/stays_pyairbnb.py:69`, `src/fetchers/stays.py:57,60`, `src/fetchers/stays_pyairbnb.py:123`, `src/templates/plan.html.j2:119` | `min_reviews=10, min_rating=4.6`, fallback `3 / 4.4`, error text `>=10 reviews and >=4.6`, header `10+ reviews and 4.6+` | Example brief sets `stays.min_rating/min_reviews` but code never reads them; template repeats literals | Read `stays.min_reviews`, `stays.min_rating` (defaults 10/4.6) in `plan.fetch_stay` -> `SP.pick`; template prints `m.stay_filters` |
| C10 | `src/plan.py:166`, `src/fetchers/stays_pyairbnb.py:82,84`, `src/templates/plan.html.j2:119` | `room_type="Entire home/apt"`, header "entire place" | Room type is a preference (families vs solo vs couples) | `stays.room_types: [entire, private, hostel]`; template from meta |
| C11 | `src/plan.py:443` | private-room budget `budget * 0.4` | Arbitrary 40% split | `stays.private_room_budget` (default 0.4 x `budget_night`) |
| C12 | `src/fetchers/stays_pyairbnb.py:34` | `beds * 2 < adults` | Bed-sharing rule is personal (friends may want 1 per bed) | `stays.guests_per_bed` (default 2) |
| C13 | `src/fetchers/stays_pyairbnb.py:98` | rooms filter `ceil(adults/2) if adults > 2` | Same assumption as C12 for bedrooms | `stays.min_bedrooms` (default `ceil(guests / guests_per_room)`) |
| C14 | `src/fetchers/stays_pyairbnb.py:82,102` | `max_pages=3`, stop at `>= 4` qualifying | Search breadth | `stays.max_pages` (internal default OK) |
| C15 | `src/fetchers/stays.py:62` | score `rating*10 - 3*per_night/budget` | Ranking weights; browser path only, pyairbnb sorts by total | Use the same sort as pyairbnb (`total` asc) for consistency |
| C16 | `src/fetchers/geo.py:91,98,104` | `PIN_DEG=0.012` (~1.3 km), default bbox `0.035`, small-place `0.2` deg | Walking radius is a preference; degrees ignore latitude | `stays.walk_radius_km` (default 1.3) converted with `cos(lat)`; `stays.search_radius_km` (default 4) |
| C17 | `src/stops.py:15,57,70,77` | `OWN_AIRPORT_KM=40`, `CENTROID_MAX_KM=40`, `TWIN_KM=50`, far-airport `200` km, `[:2]` alts | Airport-access thresholds | `flights.max_airport_km` (default 200), `flights.alt_airports` (default 2) |
| C18 | `src/fetchers/airports.py:79,81` | search radius `400` km, small-airport penalty `1.8` | Remote destinations (Patagonia, Pacific) exceed 400 km | Same `flights.max_airport_km`; penalty internal |
| C19 | `src/templates/plan.html.j2:158` | `s.airport_km > 25` | Inconsistent with `OWN_AIRPORT_KM=40` | Use `meta.own_airport_km` |
| C20 | `src/fetchers/flights_fli.py:86,127` | `PassengerInfo(adults=1)` | Prices one seat; a fare class with 1 seat left looks available for a group | `adults=people`, divide `res.price` by `people` for per-person rows |
| C21 | `src/fetchers/flights_fli.py:127`; `src/plan.py:476` | `MaxStops.NON_STOP` default; one-stop only when `flights.max_total_hours_if_stop` | Example brief writes `flights.nonstop_only: true`, never read | Read `flights.max_stops` (0/1) + `flights.max_total_hours_if_stop`; drop `nonstop_only` or map it |
| C22 | `src/fetchers/flights_fli.py:94,136,110`; `src/fetchers/flights.py:52` | `language="en"`, `&hl=en` | Locale is user input | `locale` (default `en`) |
| C23 | `src/fetchers/geo.py:27,30,54,57`; `src/fetchers/places.py:19,126`; `src/fetchers/destination.py:17`; `src/events.py:118`; `src/fetchers/visa.py:15,21`; `src/fetchers/rail.py:22` | `accept-language=en`, `en.wikivoyage.org`, `en.wikipedia.org` | English-only sources; ok default, thin coverage for some destinations | `locale` drives Nominatim `accept-language`; Wikivoyage/Wikipedia language edition list `sources.wiki_langs: [en]`, first hit wins (visa stays `en`, the article family is English-only) |
| C24 | `src/fetchers/places.py:34-36` | `DIETS` map (veg/vegan/halal/kosher/gluten-free) | Generic, but closed list; e.g. `jain`, `pescatarian` unsupported | Brief `diet: {name: {osm_tag: diet:<x>, regex: ...}}` merged over the defaults |
| C25 | `src/fetchers/places.py:257` | Overpass radius `8000 if stop.get("access") else 5000`; `access` is never set on a stop | Dead branch; radius fixed 5 km | `places.radius_km` (default 5), or derive from `stay_bbox` |
| C26 | `src/fetchers/places.py:254,245-246` | `n=8` places, `[:5]` areas/highlights | Display caps | `places.max_items` (internal default OK) |
| C27 | `src/menu.py:38,120` | `nights` default `10` | Trip length is user input | Required for `menu`; ask if absent |
| C28 | `src/menu.py:70` | suggested nights `2 + min(2, len(musts)//6)` | Heuristic; fine as a suggestion | `menu.min_nights_per_stop` (default 2) |
| C29 | `src/menu.py:69,87` | access transfer `> 40` km, "costs a transfer day" `> 60` km | Same thresholds as C17, duplicated | Reuse `stops.OWN_AIRPORT_KM` / brief value |
| C30 | `src/menu.py:77-78` | event window `start + 40 days` | Ignores the trip window `end`; shows events after the trip | Use `(start, end)` from `_window(cfg)` |
| C31 | `src/menu.py:134,150,163-164` | `half = n//2 + 2`, live stays for `cands[:6]`, combos of `(2,3,4)` over `cands[:7]`, `nights + 1` slack | Search breadth | `menu.combo_sizes`, `menu.live_candidates` (defaults as now) |
| C32 | `src/fetchers/advisory.py:24-25` | `SOURCES = {GB, US, CA}`, `THIRD_COUNTRY = [FCDO, US]` | Indian passport (this trip) gets third-country advisories; correct and labelled, but AU/DE/IE/NZ governments publish feeds | Add adapters: AU `https://www.smartraveller.gov.au/destinations-export` (JSON, unverified), DE `https://www.auswaertiges-amt.de/opendata/travelwarning` (JSON, unverified). Allow brief `advisory.sources: [FCDO, US]` override. Cache 24 h (currently uncached) |
| C33 | `src/fetchers/advisory.py:28-29,33` | FCDO slug from English country name | Names with diacritics/"The" mismatch (`Côte d'Ivoire`, `The Gambia`) | Use the GOV.UK search API `https://www.gov.uk/api/search.json?filter_format=travel_advice&q=<name>` to get `link` (unverified) |
| C34 | `src/fetchers/climate.py:15,21-24` | `YEARS=5`, rain-day bands `15/8`, hot `35 C`, cold `3 C` | Derived warning thresholds; personal comfort | `climate.years`, `climate.hot_c`, `climate.cold_c` (defaults as now) |
| C35 | `src/fetchers/misc.py:77,79` | `forecast_days=16`, `> 15` days | Open-Meteo API limit, not a preference | none (OK, but name the constant) |
| C36 | `src/events.py:56-57` | event keyword list `festival|...|christmas|lantern|fireworks|...` | Western/Asian cue words; misses e.g. `Diwali`, `Eid`, `Holi`, `Songkran`-style local names | Prefer section-based extraction (`section_mentions`, already present) and drop `mentions()` keyword path from `menu`, or add `events.keywords` brief key |
| C37 | `src/events.py:175` | new-moon dates `[]` | Lunar calendar events tied to new moon (e.g. Lunar New Year, Diwali) never dated | Compute new moons from the same `SYNODIC` / `NEW_MOON_REF` |
| C38 | `src/fetchers/rail.py:24` | night window `22:00-05:00` | Personal | `ground.night_hours: ["22:00", "05:00"]` |
| C39 | `src/fetchers/rail.py:144,158` | `rows[:5]`, `limit=420` chars | Display caps | internal (OK) |
| C40 | `src/fetchers/photos.py:15,20,32,42-43` | `BAD` regex, `gsrlimit 30`, min width `1400`, `1200` px, `quality=76` | Render settings | internal (OK) |
| C41 | `src/cache.py:20-21` | TTLs flights 8 h, stays 24 h, hostels 12 h, fx 24 h, places/climate/ground 7 d, geo/visa/holidays 30 d | Sensible; visa 30 d is long when rules change (e.g. visa-free windows); ground fares share the 7 d bucket with OSRM | `cache.ttl` override map in brief or env; split `ground:12go` (24 h) from `ground:osrm` (30 d); visa 7 d |
| C42 | `src/money.py:16-24` | `SYMBOLS` ISO 4217 table | Static, partial | `babel.numbers.get_currency_symbol(code, locale)` (CLDR) with ISO-code fallback; or keep (low impact) |
| C43 | `src/browser.py:14` | `NODE_BIN = "/opt/homebrew/opt/node@24/bin"` | macOS-Homebrew path; wrong on Linux/Windows/Intel Mac | `shutil.which("node")`; env `TRIPFORGE_NODE_BIN` stays as override |
| C44 | `src/browser.py:44` | viewport `1400x1000`, `goto` waits `4000/4500` ms, timeout `45000` | Scraper tuning | internal (OK) |
| C45 | `src/templates/plan.html.j2:72` | "Food, drinks and tours come on top (estimates below)" | Claims estimates exist even when `spend_note` placeholder applies | Condition on `first.totals.spend_note` |
| C46 | `src/cli.py:21,67-68` | `BRIEF_KEYS` whitelist, then `(td / "brief.yaml").write_text(...)` | `plan --brief X` **overwrites the user's brief** with only whitelisted keys: drops `nights`, `month`, `max_ground_hours`, `alt_starts`, `optional_cards`, comments. Next `menu` run then falls back to `nights: 10` (C27) | Never rewrite an existing brief; write the merged config to `out/brief.resolved.yaml`. Only `--trip` without `--brief` creates `brief.yaml` |
| C47 | `trips/example-thailand/brief.yaml:8,10,13,15,18-21,23,27,30-40` | keys `alt_starts`, `leave_days_max`, `nonstop_only`, `cabin_only`, `stays.budget_night`, `hostels_ok`, `min_rating`, `min_reviews`, `food`, `frugal`, `optional_cards`, `must_consider` | None of these are read by code (code reads `alt_start`, top-level `budget_night`, `hostels`); the canonical example brief silently does nothing for half its fields | Adopt the schema below, validate with a JSON Schema (`pydantic` model) in `cli.load_brief`, warn on unknown keys |
| C48 | `.gitignore:12`, `trips/thailand-final-27-4/`, `-28-5/`, `-v2/`, `-v3/`, `thailand-dec26-test/`, `lisbon-porto-smoke/` | personal trip folders inside the public repo checkout (ignored, not tracked) | One `git add -f` from leaking passport, home airport, dates | Default `TRIPFORGE_HOME` to `~/.tripforge` (or `~/trips`) instead of the repo root (`cache.py:27-40`); keep only sanitised examples in `trips/` |

### Counts

| Severity | Rows |
|---|---|
| A | 11 |
| B | 15 |
| C | 48 (of which 6 marked OK/internal: C7, C35, C39, C40, C44, C14) |

---

## Proposed brief.yaml schema

Legend: **R** = user must supply, **A** = ask once if absent (planner asks, CLI errors), **D** = derived/fetched (user may override), **O** = optional preference with default.

```yaml
# ---- who and where from
home:                      # R: one of
  iata: <IATA>             #   home airport, or
  city: <name>             #   resolved via Nominatim -> airports.nearest (geo 30 d)
people: <int>              # R  travellers splitting cost
passport: <ISO2>           # D  default: home airport country (OurAirports iso_country)
currency: <ISO4217>        # D  default: money.country_currency(home cc) (Wikidata, 30 d)
locale: en                 # O  drives Google Flights hl, Nominatim accept-language, wiki edition order

# ---- when
start: <YYYY-MM-DD|+Nd>    # R  (+60d relative allowed for regression briefs)
alt_start: [<date>...]     # O  extra start dates to compare
nights: <int>              # R for menu; D for plan (sum of stop nights)
leave_days_max: <int>      # O  used with home public holidays (Nager.Date) to rank start dates

# ---- where
destination: <text>        # R for menu (country/region; destination.resolve -> Wikivoyage)
stops: "Name[/Area]:N[@IATA],..."   # R for plan (picked from menu.json combos)
end_airport: <IATA>        # O  default: last stop's primary airport
country: <name>            # D  hint for stop geocoding; default destination's country

# ---- preferences
prefs: [<tag>...]          # O  free tags; vibe score + places sections
diet: [veg|vegan|halal|kosher|gluten-free|<custom>]   # O  replaces "veg" inside prefs
diet_tags: {<custom>: {osm: "diet:<x>", regex: "<re>"}}  # O
pace:
  sights_per_day: 3        # O
  earliest_departure: "08:00"   # O
nightlife: false           # O  explicit; replaces inference from prefs/party_rate

# ---- money the user decides (never fetched, never defaulted)
budget:
  stay_per_night: <amount> # O  0/absent = no cap
  private_room_per_night: <amount>   # O  default 0.4 x stay_per_night
spend:                     # O  section is a placeholder until meal_rate is set
  meal_rate: <amount>
  meals_per_day: 3
  party_rate: <amount>     # A if nightlife true
  party_nights: <int|{Stop: int}>   # O  default ceil(nights x party_share)
  party_share: 0.5
  transport_day: <amount>
split: equal               # O  equal | {person: weight}; used for stays/ground shares

# ---- flights
flights:
  max_stops: 0             # O  0 nonstop, 1 one-stop
  max_total_hours_if_stop: <h>  # O
  max_airport_km: 200      # O
  alt_airports: 2          # O
  backend: auto            # O  auto | fli | browser

# ---- stays
stays:
  guests: <int>            # D  default people
  room_types: [entire]     # O  entire | private | hostel
  min_rating: 4.6          # O
  min_reviews: 10          # O
  guests_per_bed: 2        # O
  walk_radius_km: 1.3      # O  for "City/Area" pins
  search_radius_km: 4      # O
  hostelworld: {Stop: [id, ...]}   # O override; default discovered (A10)
  backend: auto            # O

# ---- ground
ground:
  max_hours: 6             # O  ground instead of flight when OSRM duration <= this
  max_km: 350              # O  pre-filter
  rail_ok: false           # O
  rail_max_hours: 18       # O
  night_travel_ok: true    # O
  night_hours: ["22:00", "05:00"]  # O
  ferry_kmh: 30            # O  only when no aggregator duration

# ---- sources / caching
advisory: {sources: auto}  # O  auto = passport-keyed; or [FCDO, US, CA, AU, DE]
cache: {ttl: {fx: 24h, flights: 8h, stays: 24h, visa: 7d}}   # O
browser: headless          # O  headless | attach

# ---- written by tripforge, never by hand (out/brief.resolved.yaml)
resolved:
  home: {iata, city, cc, lat, lon}
  currency: <ISO4217>
  fx: {<SRC>: {rate, date, url}}      # Frankfurter, 24 h
  stops: [{name, lat, lon, cc, iata, airport_km, alt_airports, stay_center, hostelworld_ids}]
  fetched_at: <ISO>
```

Must supply (R): home (`iata` or `city`), `people`, `start`, and `destination` (menu) or `stops` (plan); `nights` for menu. Must decide when the matching section is wanted (A): `spend.meal_rate`, `spend.party_rate` when nightlife is on. Everything else is derived or defaulted.

## Fetch pipeline

1. **Validate brief** (`cli.load_brief` + schema). Resolve relative dates. Never rewrite `brief.yaml`; write `out/brief.resolved.yaml`.
2. **Home**: `airports.resolve_home` -> `{iata, cc}`; `money.resolve_currency` (Wikidata, `geo` 30 d); `passport` default = cc. Writes `resolved.home`, `resolved.currency`.
3. **Destination (menu)**: `destination.resolve(text)` -> Wikivoyage title; `wikivoyage(title).destinations` -> candidates; per candidate `stops.resolve` (Nominatim + OurAirports + `guide`). Writes `menu.json.candidates`.
4. **Stops (plan)**: `stops.parse_spec` -> per stop `geocode` / `geocode_point` (pinned area), `airports.nearest`, `guide` (areas, highlights, stay centre). Writes `resolved.stops`.
5. **Hops**: `plan.transitions` -> per hop `ground.route` (OSRM, 30 d) first; ground if `duration_h <= ground.max_hours` else fly (fixes C4).
6. **Prices, in parallel (thread pool, polite rate limits)**:
   - flights: `flights_fli.fetch_leg` per (orig, dest, date) incl. menu hops and return (A7, A8); one-stop fallback; browser fallback for primary pairs. `flights` 8 h.
   - stays: `stay_bbox` -> `stays_pyairbnb.fetch_stay` with brief filters (C9-C13). `stays` 24 h.
   - hostels: `hostels.discover(stop)` (suggestions API -> city page ids, `hostels:discover` 30 d) -> `fetch_hostel` per id. `hostels` 12 h.
   - ground fares: country-keyed fare adapter (A1) -> `fare` or `None` + link. `ground:fare` 24 h.
   - rail: country adapter, default Transitous (A3). `ground` 7 d.
7. **Context, in parallel**: `money.country_currency` per stop country; `money.rate` (Frankfurter v1, 24 h, B1); `visa_requirement` for foreign stops (7 d); `fetch_advisories` (passport-keyed, 24 h); `fetch_normals` (Open-Meteo archive, 7 d); `fetch_weather` inside 16 days; `public_holidays` for home + stop countries (30 d); Wikivoyage/Wikipedia events + `lunar_rows` (full and new moon); `stop_places` (Overpass + Wikivoyage, 7 d); `fetch_photos`.
8. **Assemble** `out/plan.json`: every row carries `source_url`, `fetched_at`, `backend`, `cached`; totals only from read prices; missing reads counted as `*_missing`, never estimated; daily spend only from `spend.*`.
9. **Render** (`render.py` + `plan.html.j2`): template reads labels and thresholds from `plan.meta` (filters, room types, fare source name, own-airport km) instead of literals (A2, C9, C10, C19, C45); `render` re-runs from `plan.json` without refetching.
10. **Evidence**: screenshots and raw JSON under `trips/<slug>/evidence/`, trip folders under `TRIPFORGE_HOME` outside the repo (C48).
