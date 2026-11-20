# trip.json: the one file an AI (or a person) fills to get a trip site

Read this before writing `trips/<slug>/site/trip.json`. The template is destination-agnostic; every fact comes from this file,
`data/plans.json` (researched day plans) and `img/` (photos you fetched). Never put passport numbers, bank details or full
names of travellers who did not agree to appear; the build refuses the page if a passport-shaped token slips in.

```jsonc
{
 "trip": {
  "slug": "goa",                      // URL path /goa/ and the cookie path
  "name": "Goa", "home": "NAG",        // header title; home airport code shown on the Runway strip
  "start": "2026-11-22", "end": "2026-11-30",
  "tz": "Asia/Kolkata", "homeTz": "Asia/Kolkata",   // two clocks appear when they differ
  "cur": "<ISO 4217>", "sym": "<symbol>", "homeCur": "<ISO 4217>", "homeSym": "<symbol>",   // features.fx turns on automatically when cur != homeCur
  "people": [{"k":"PR","n":"Pranay"}, {"k":"MU","n":"Muskan"}],  // k = short code stored on ledger entries
  "split": "equal" | "none",           // equal: per-person balances and ÷n key; none: one running total, no payer shown
  "categories": {"food":["🍜","Food"],"stay":["🛏","Stay"]},  // optional; spend tags on ledger entries. Default: travel/stay/food/party/leisure/shopping/other
  "budget": 155000,                    // expected spend: per person when split=equal, whole trip when none
  "defaultTheme": "beach",             // party | party-drinks | party-smoke | beach | birthday | pg13 | mountain | city | plain | <custom>
  "visitorTheme": "pg13",              // used only when features.visitorRole
  "features": {"visitorRole": false},  // visitorRole: a read-only PIN that hides Money and filters party/late slots
  "speakLang": "th",                   // BCP-47 prefix for the "Say it" button; omit when nothing needs reading aloud
  "roadKmh": 25, "greeting": "Susegad", "planSource": "Sourced from Wikivoyage, venue pages and 2025–26 press."
 },
 "data": {
  "events":  [ {kind:"fly"|"stay"|"road"|"rail"|"bus"|"boat", t:ISO-with-offset, from,to,fc,tc,name,dep,arr,st:"ok"|"open"|"none", q:"maps query", note} ],
  "stays":   { key: {name, sub, st, ref, book, site, pics:n, addr, q, la, lo, local:"address in local script", note} },
  "days":    [ {img, where, wx:"city key in cities", h:"title", p:"paragraph", sleep:"stay key" | null, sleepNote,
               move:[{kind, from,to,dep,arr,name,st,ref,sub,q}], go:[{n,la,lo}], tix:["group",...], tpl:"template id", tplh:"heading", opts:[...]} ],
  "tix":     { group: [ {n, p:"price/hours line", u:"https://..."} ] },      // rendered as the Tickets panel; link text is book / map / info by URL
  "cred":    { img: "Photographer, licence" },
  "cities":  [ ["Morjim", 15.63, 73.73] ],  "typical": { "Morjim": "Typical late Nov · 33° / 22° · dry" },
  "icao":    { "6E": "IGO" },               // airline IATA -> ICAO for the flight tracker fallback link
  "todo": [...], "pack": [...], "todoTitle": "Before you go",   // todoTitle optional, default "Before we fly"
  "driver":  [ {cap, name, local, en, q, tel} ],   // Show-the-driver cards
  "kit":     [ {title, kind:"kv"|"call", rows:[{t, d, u, l, linkTitle:true, ref, pill, pillClass, tel, telLabel}], note} ],
  "phrases": [ ["local script","romanised","meaning"] ],  "phrasesTitle": "Say it in Thai, tap to hear",
  "smarts":  [ "one line each" ],
  "quick":   [300, 500, 1000, 2500, 5000],  "spendExample": "Dudhsagar jeep",
  "fares":   {title, rows:[[leg, price]], note},
  "budget":  {rows:[[label, "<sym>43,000"]], total:"<sym>1,55,000", note},
  "runway":  {img, headsup:[{t, d, u, l}], open_table:{title, head:[...], rows:[[...]], note}},
  "templates": [ {id:"nye", html:"<div class=\"panel\">...</div>"} ],   // referenced by days[].tpl
  "themeAccents": { "beach": {"accent":"#2fc4b2","ink":"#06211c"} },  // per-theme accent override
  "themes": { "custom": {"name":"Custom","deco":["🎿","❄️"],"stk":["🎿"],"pg":true} },  // extra themes
  "lockSub": "Morjim · Baga", "foot": "...", "extraCss": ""
 },
 "hosting": {"pin": "1806", "port": 8766},
 "private_patterns": ["Punyani"]        // extra regexes the build must not find in the page (surnames, PNR shapes)
}
```

## Where each thing comes from
| Field | Source |
|---|---|
| events, stays, days[].move | the user's bookings (vouchers, PNR mails). Flight times from the airline's current itinerary, not the original ticket. |
| days[].h / p / go | `out/plan.json` stops + the research JSON; weekdays are computed from the date, never typed |
| data/plans.json | `tripforge site merge-plans trips/<slug>` from `research/*.json` (schema in `agents/RESEARCH_BRIEF.md`) |
| img/*.jpg | Wikimedia Commons, CC-licensed, landscape, no people as subject; record credits in `cred` |
| cities / typical | the stay towns; typical climate from the climate fetcher or a climate table |
| fares / budget / todo / pack / smarts / kit | written from the brief and research; every price is a range from a source |
| hosting.pin | chosen by the user; never reuse across trips |

## Static vs dynamic
- Static in the build: dates, bookings, copy, photos (a rebuild per change).
- `data/*.json`, fetched by the page: plans.json (research), flights.json (server poller). Replace without a rebuild.
- Live from the phone: FX (frankfurter.dev, open.er-api.com), weather (Open-Meteo), GPS distances, the ledger API.

## Workflow for an agent
0. `tripforge site check trips/<slug>` is the deploy gate (syntax, private data, dist drift); run it before every upload.
1. `tripforge site init trips/<slug>` -> skeleton with the brief's dates, people and currency.
2. Fill `trip.json` from bookings + plan; run the research brief; `tripforge site merge-plans`; fetch photos into `site/img/`.
3. `tripforge site build trips/<slug>` -> `site/dist/`. Fix anything the build refuses (JS syntax, private data).
4. Screenshot at 390px with Playwright, check console errors, look at the pixels.
5. `tripforge site host trips/<slug>` prints the server steps for the hosting owner.

## `data.sections` (optional): independent parts of the page, each its own JSON file
```jsonc
"sections": [{"id": "flights", "title": "Flights", "kind": "flightPlan", "src": "flights.json", "every": 300},
             {"id": "itinerary", "title": "Itinerary", "src": "itinerary.json"}]   // src: path relative to trips/<slug>/
```
`tripforge site sync trips/<slug>` (add `--watch 30` to keep going) prepares each `src` into `site/data/<id>.json` concurrently; copy that folder
to the host and the page picks it up without a rebuild. The page fetches every section on its own request and refresh clock (`every`
seconds, default 300, plus when the tab returns), with an 8 s timeout, so one slow or missing section shows "Coming soon" while the rest work.
Kinds: `dayGuide` (below); `flightPlan` (below); `itinerary` ({verdict, days[{label, assumption, blocks[{time,title,place,why,link}]}], stays[{place, options[]}], transfer, getting_around, rules_to_flag, visa, budget{lines,total_inr}, unverified[], assumptions[]}; estimates carry a visible "est" pill); `stays` ({places:[{place, dates, top_pick:{name,url,price/est_inr,rating,area,why,verified}, runner_up:{...}}]}; every listing links out and shows "unverified" unless `verified: true`; once it loads it replaces the itinerary's estimated stays); `book` ({legs:[{who, flight, price_<cur>, available|availability, url, checked_at}], total_<cur>, checked_at}: availability pill, booking link, new total); `brief` ({summary{who, dates, route, total, book_first[{t,u,d}], checks[{t,ok}]}, assumptions[{t,d}|text], changes[{t,d}], budget{rows[[label,value,note]], total, note}}: the assumptions box, a folded "What changes if" list and a rough budget); a section may set `pending` (text shown while its file is missing); anything else is rendered generically (lists become cards, objects become lines, links become links).
Add a kind by adding a renderer to `SEC_RENDER` in `js/20-sections.js` and, if the source needs preparing, a processor in `sections.py`.

## `dayGuide` section: hour-by-hour days with places, transport, meals, backups and budgets
Use for a real daily guide. The author writes local-currency numbers and names; `dayguide.py` converts with the dated `fx`, builds a Google Maps search link for every item with a `name` (+ `area`) unless it gives its own `maps` pin, and refuses bad times, non-https links and a missing rate date.
```jsonc
{"fx": {"from": "THB", "to": "INR", "rate": 2.7489, "date": "20 Nov 2026", "source": "https://..."},   // required, dated
 "intro": "one line",
 "days": [{"id": "d1", "tab": "Sat 21", "date": "2026-11-21", "title": "Sat 21 Nov: ...", "summary": "...", "warn": ["red line"],
   "timeline": [{"time": "18:10", "end": "18:50", "title": "Land", "kind": "fly|move|eat|drink|beach|see|rest|book|night",
                 "name": "place", "area": "district", "why": "one line", "hours": "09:00-17:00", "cost": [100, 200],   // number or [low, high], local currency
                 "how": "text" | {"text": "Airport rail", "mins": 30, "cost": 45}, "tip": "...", "url": "booking/info https", "src": "evidence https", "verified": false}],
   "eat": [{"meal": "Dinner", "name": "...", "area": "...", "why": "...", "order": [{"dish": "pad thai", "cost": 80}], "hours": "...", "cost": [300, 600]}],
   "nightlife": [{"time": "22:00", "name": "...", "entry": [300, 500], "drinks": [200, 350], "dress": "...", "safety": "..."}],
   "do": [{"name": "...", "kind": "beach", "why": "...", "url": "https://...", "cost": 1700}],
   "backup": {"title": "Rain or low-energy backup", "text": "...", "items": [{"name": "...", "cost": 150}]},
   "budget": {"rows": [{"item": "Food", "cost": [800, 1500]}, {"item": "Airport train", "home": 250}], "note": "..."},   // cost = local currency, home = already home currency; totals are computed
   "book": [{"t": "Boat tour", "u": "https://...", "d": "refundable"}], "notes": ["..."]}]}
```
Times must be HH:MM and ascending; a small hour after 18:00 counts as next day. An item is "unverified" (visible badge, cost shown as "est ...") unless it says `verified: true`. The page opens on today's day when today is a trip day (trip timezone), else the first, and a day selector switches days without scrolling.

## `flightPlan` section: per-person flights with rule checks
Use when travellers fly separately (different origins or return cities). Each option is one complete set of legs;
every option is checked against `rules`, shown with ✓ / ! / ✗ per rule, and the best option
(fewest hard failures, then cheapest) is marked. See `src/tripforge/site/flightplan.py`. `site check` fails when an option marked `recommended` breaks a hard rule.
```jsonc
{
  "title": "Flights", "note": "Prices: source and fetch time",
  "rules": [
    {"type": "not_earlier",   "leg": "out-b", "than": "out-a", "label": "B lands no earlier than A"},
    {"type": "within",        "legs": ["out-a", "out-b"], "minutes": 30, "soft": true, "label": "Land together"},   // soft: warning only
    {"type": "arrive_before", "leg": "back-b", "time": "19:00", "label": "B home before 19:00"},                 // local arrival time
    {"type": "arrive_on",     "leg": "back-b", "date": "2026-11-24", "label": "Same-day return"},
    {"type": "max_fare",      "max": 25000, "label": "No flight over 25,000 per person"}   // per leg price / pax; legs get cap.headroom, options over it are greyed "Over budget"
  ],
  "options": [{"id": "day", "label": "Daytime pair", "recommended": true,   // recommended options must pass hard rules or `site check` fails
    "legs": [{"role": "out-a", "who": "A", "dir": "Out", "flight": "XX 123", "from": "AAA", "to": "BBB",
              "dep": "2026-11-21T12:20+05:30", "arr": "2026-11-21T18:10+07:00", "price": 18780}]}]
}
```
`verified`: true on a leg, an option or the whole plan marks it checked against the airline or fare source; anything else shows an "unverified" pill, and the page upgrades itself when the file changes to `verified: true`.
`chosen`: an option id the travellers picked; it is shown alone on top with a "chosen plan" pill and the rest fold under "Other options".
`dep` / `arr` are ISO times with each airport's own offset, so cross-timezone comparisons are exact.
