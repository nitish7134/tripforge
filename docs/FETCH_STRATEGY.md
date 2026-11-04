# Fetch strategy: what a trip plan needs to know, and how each thing is found

tripforge ships **no travel data**. It ships a strategy: for every piece of information a plan needs, which source answers it, how it is queried, what the fallback is, and how the result is tagged. Place names, fares, phrases and tips only ever come from a fetch made for the trip in hand, with a URL and a fetched-at time. Anything that cannot be fetched is rendered as `unavailable (reason, link)`, never guessed.

The planner agent (`agents/PLANNER_PROMPT.md`) follows the same table when it researches by hand.

## The table

| Information need | Decided by | Primary source and method | Fallback | Tag |
|---|---|---|---|---|
| Is this section even relevant? (visa, FX, advisory, SIM, flights vs ground) | home country vs every stop's country; trip length; reachability by road/rail | resolved geography (Nominatim country for stops, airport database for home) | always decidable | n/a; omitted sections are listed once as "not applicable: reason" |
| Home country, currency, locale, demonym | home airport ISO country | Wikidata SPARQL from the ISO code | ask the user | live |
| Which Wikivoyage article covers a free-text destination | brief `destination` (e.g. `Region, Country`) | try the text as given, then without the trailing `, Country`, then Wikivoyage opensearch, then Nominatim's name + a Wikivoyage search; the first page that exists wins | `no article found for X; tried A, B, C` (never a stack trace) | live |
| Candidate stops for a region | the resolved article | its Cities / Other destinations sections (multi-line `{{marker}}` templates are flattened first, entities unescaped); Nominatim for coordinates | Wikipedia article | live (community) |
| Nearest airports to a stop | stop coordinates | airport database (open data CSV, refreshed monthly), radius from brief | none | live |
| Flights per leg | home/stop airports, dates, brief `nonstop_only` / `max_total_hours` | Google Flights structured query with region = home country and currency = trip currency; flight number, times, duration, fare | browser page read of the same query | live |
| Alternative departure dates | brief `alt_starts` or ±3 days | same flight query per date | none | live |
| Stays | stop coordinates, dates, people, brief budget, rating and review floors, room types (entire / private / hostel). A stop written `City/Area` pins the search to that geocoded area at walking radius (~1.3 km) instead of the city's Wikivoyage stay centre | Airbnb search (bbox, dates, filters) | browser page read; hotel/hostel sources when configured | live |
| Hostel beds and private rooms | brief `stays.hostelworld: {Stop: [property ids]}` (the number in a hostelworld.com property URL), dates, guests | Hostelworld public property + availability endpoints: name, rating /10, review count, per-room lowest nightly and total price, beds left, deposit % | row reads unavailable with the property link | live |
| Ground legs between stops | both stops' coordinates | routing API for road existence and duration; water between → ferry with duration from distance; rail mention in the destination's Wikivoyage "Get in" | duration only; **no money from heuristics** | live (duration) |
| Rail between two places in one country (brief `ground.rail_ok`) | both city names, the date, country, brief `ground.night_travel_ok` / `ground.rail_max_hours` / `pace` | a per-country rail-quote adapter (`fetchers/rail.py` `ADAPTERS`, keyed by ISO country). Station codes come from the station's Wikipedia infobox. India: erail.in timetable read (train number, name, departure, arrival, duration, classes). Other countries: no adapter yet, the row reads unavailable with the pointer to add one (candidates: the national operator's or an aggregator's public timetable page). Plus the destination's Wikivoyage `Get in > By train` text quoted with its link | `unavailable` with the source URL when blocked or no direct train; **never a fare estimate** (fares are read only when a page labels them; erail's packed per-class fares are not parsed) | always `indicative` |
| One-stop flight when no nonstop exists | brief `flights.max_total_hours_if_stop` | fli with `MaxStops.ONE_STOP_OR_FEWER`, keep two-leg itineraries within the total-time limit, show the connecting airport | `unavailable` | live |
| Which leg the totals use | priced nonstop, else priced one-stop, else the first rail row that fits the brief (its fare counted as missing, never estimated); road rows are shown beside, never totalled | arithmetic on the rows above | n/a | n/a |
| Ground fares | the two stops | transport aggregator page for the pair ("from" price floor, duration) | "fare unavailable" with the link | live floor or unavailable |
| Things to see and do, with fees | each stop | Wikivoyage See / Do listings (price field), OSM tourism tags | Wikipedia article summary | live (community) |
| Food that matches dietary prefs | brief `prefs` (veg, vegan, halal, kosher, gluten-free, any tag) | Wikivoyage Eat section (phrases and listings), OSM `diet:*` tags near the stay centre | none; say "no tagged places found" | live |
| Nightlife and party areas | brief `prefs` | Wikivoyage Drink section, OSM `amenity=bar/nightclub/pub` | none | live |
| Where to stay inside a city | stop | Wikivoyage Districts / Sleep sections; Nominatim neighbourhoods | centre of the stop | live |
| Local transport prices and scams | stop | Wikivoyage Get around and Stay safe sections (quoted with revision date) | none | community, dated |
| Events in the window | dates, each stop and the home country | public-holiday API for both countries (a domestic trip's single country is read once and labelled for both leave planning and closures); each stop's and the region's Wikivoyage `Events` / `Festivals` section bullets that name a month in the window; Wikipedia search hits split from glued `Name, Place (Month)` text into one event each; moon-dated events only if an article mentions one | none | live / community |
| Climate for the dates | stop coordinates, month | weather normals API (rain days, highs, lows, sunshine) → one derived warning sentence | forecast API inside 16 days | live |
| Visa | passport country vs each stop's country | Wikipedia "Visa requirements for <demonym> citizens" article row | unavailable with link | community, dated, always "verify" |
| Travel advisory | passport country | that government's own feed (UK, US, AU, CA known); otherwise two third-country feeds labelled as such | none | live |
| FX | home vs destination currency (skipped if equal) | ECB rates API | none | live |
| What travellers say recently | destination | Reddit RSS (search and thread feeds; the JSON API is often blocked), labelled "what people say" with links | skip | community |
| Photos | stop | Wikimedia Commons search with attribution | none | live |
| Daily spend | brief `meal_rate`, `party_rate`, people, nights | arithmetic on the brief only | placeholder asking for the rates | from brief |

## Where fetched data lives

Everything fetched for a trip is consolidated in that trip's folder: `trips/<slug>/out/plan.json` (every row with source URL and fetched_at), `trips/<slug>/evidence/` (screenshots and raw JSON), `trips/<slug>/notes.md` (decisions). Trip folders are the only place where concrete places, fares and tips may be stored, because they are specific to one trip and are cleaned up with it. `src/` holds strategy and code only.

## Rules the table implies

1. **A fetch is keyed by the trip.** Same source, different trip, different query. Nothing is remembered across trips except the cache, which is keyed by the exact query and expires.
2. **Heuristics may produce time, never money.** A distance can give a duration estimate; a fare must be read from a page or left unavailable.
3. **Community text is quoted, dated and linked.** Wikivoyage, Wikipedia and Reddit are "what people say", not fact; show the revision or post date.
4. **Every omitted section is explained.** A domestic trip shows "visa: not applicable (domestic)" once, so the reader knows it was considered.
5. **Region and currency follow the home country.** No default country, airport, currency or language anywhere in code.
6. **When a source dies, the cell goes unavailable.** Sources break (APIs deprecate, pages change). The plan must stay honest rather than fall back to stale tables.

## Sources known to be unusable (so nobody re-adds them)

Deprecated or keyed: restcountries.com, Amadeus self-service. Blocked by bot protection: airportia.com, flightsfrom.com, Reddit JSON API from many networks (RSS works). Broken by page changes: the openbnb Airbnb MCP server.
