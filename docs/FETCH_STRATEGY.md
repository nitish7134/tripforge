# Fetch strategy: what a trip plan needs to know, and how each thing is found

tripforge ships **no travel data**. It ships a strategy: for every piece of information a plan needs, which source answers it, how it is queried, what the fallback is, and how the result is tagged. Place names, fares, phrases and tips only ever come from a fetch made for the trip in hand, with a URL and a fetched-at time. Anything that cannot be fetched is rendered as `unavailable (reason, link)`, never guessed.

The planner agent (`agents/PLANNER_PROMPT.md`) follows the same table when it researches by hand.

## The table

| Information need | Decided by | Primary source and method | Fallback | Tag |
|---|---|---|---|---|
| Is this section even relevant? (visa, FX, advisory, SIM, flights vs ground) | home country vs every stop's country; trip length; reachability by road/rail | resolved geography (Nominatim country for stops, airport database for home) | always decidable | n/a; omitted sections are listed once as "not applicable: reason" |
| Home country, currency, locale, demonym | home airport ISO country | Wikidata SPARQL from the ISO code | ask the user | live |
| Candidate stops for a region | brief `destination` | the region's Wikivoyage article: Cities / Other destinations sections; Nominatim for coordinates | Wikipedia article | live (community) |
| Nearest airports to a stop | stop coordinates | airport database (open data CSV, refreshed monthly), radius from brief | none | live |
| Flights per leg | home/stop airports, dates, brief `nonstop_only` / `max_total_hours` | Google Flights structured query with region = home country and currency = trip currency; flight number, times, duration, fare | browser page read of the same query | live |
| Alternative departure dates | brief `alt_starts` or ±3 days | same flight query per date | none | live |
| Stays | stop coordinates, dates, people, brief budget, rating and review floors, room types (entire / private / hostel) | Airbnb search (bbox, dates, filters) | browser page read; hotel/hostel sources when configured | live |
| Ground legs between stops | both stops' coordinates | routing API for road existence and duration; water between → ferry with duration from distance; rail mention in the destination's Wikivoyage "Get in" | duration only; **no money from heuristics** | live (duration) |
| Ground fares | the two stops | transport aggregator page for the pair ("from" price floor, duration) | "fare unavailable" with the link | live floor or unavailable |
| Things to see and do, with fees | each stop | Wikivoyage See / Do listings (price field), OSM tourism tags | Wikipedia article summary | live (community) |
| Food that matches dietary prefs | brief `prefs` (veg, vegan, halal, kosher, gluten-free, any tag) | Wikivoyage Eat section (phrases and listings), OSM `diet:*` tags near the stay centre | none; say "no tagged places found" | live |
| Nightlife and party areas | brief `prefs` | Wikivoyage Drink section, OSM `amenity=bar/nightclub/pub` | none | live |
| Where to stay inside a city | stop | Wikivoyage Districts / Sleep sections; Nominatim neighbourhoods | centre of the stop | live |
| Local transport prices and scams | stop | Wikivoyage Get around and Stay safe sections (quoted with revision date) | none | community, dated |
| Events in the window | dates, each stop and the home country | public-holiday API for both countries; Wikivoyage/Wikipedia festival mentions for each stop; moon-dated events only if an article mentions one | none | live / community |
| Climate for the dates | stop coordinates, month | weather normals API (rain days, highs, lows, sunshine) → one derived warning sentence | forecast API inside 16 days | live |
| Visa | passport country vs each stop's country | Wikipedia "Visa requirements for <demonym> citizens" article row | unavailable with link | community, dated, always "verify" |
| Travel advisory | passport country | that government's own feed (UK, US, AU, CA known); otherwise two third-country feeds labelled as such | none | live |
| FX | home vs destination currency (skipped if equal) | ECB rates API | none | live |
| What travellers say recently | destination | Reddit RSS (search and thread feeds; the JSON API is often blocked), labelled "what people say" with links | skip | community |
| Photos | stop | Wikimedia Commons search with attribution | none | live |
| Daily spend | brief `meal_rate`, `party_rate`, people, nights | arithmetic on the brief only | placeholder asking for the rates | from brief |

## Rules the table implies

1. **A fetch is keyed by the trip.** Same source, different trip, different query. Nothing is remembered across trips except the cache, which is keyed by the exact query and expires.
2. **Heuristics may produce time, never money.** A distance can give a duration estimate; a fare must be read from a page or left unavailable.
3. **Community text is quoted, dated and linked.** Wikivoyage, Wikipedia and Reddit are "what people say", not fact; show the revision or post date.
4. **Every omitted section is explained.** A domestic trip shows "visa: not applicable (domestic)" once, so the reader knows it was considered.
5. **Region and currency follow the home country.** No default country, airport, currency or language anywhere in code.
6. **When a source dies, the cell goes unavailable.** Sources break (APIs deprecate, pages change). The plan must stay honest rather than fall back to stale tables.

## Sources known to be unusable (so nobody re-adds them)

Deprecated or keyed: restcountries.com, Amadeus self-service. Blocked by bot protection: airportia.com, flightsfrom.com, Reddit JSON API from many networks (RSS works). Broken by page changes: the openbnb Airbnb MCP server.
