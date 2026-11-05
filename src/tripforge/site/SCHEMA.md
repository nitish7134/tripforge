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
  "todo": [...], "pack": [...],
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
1. `tripforge site init trips/<slug>` -> skeleton with the brief's dates, people and currency.
2. Fill `trip.json` from bookings + plan; run the research brief; `tripforge site merge-plans`; fetch photos into `site/img/`.
3. `tripforge site build trips/<slug>` -> `site/dist/`. Fix anything the build refuses (JS syntax, private data).
4. Screenshot at 390px with Playwright, check console errors, look at the pixels.
5. `tripforge site host trips/<slug>` prints the server steps for the hosting owner.
