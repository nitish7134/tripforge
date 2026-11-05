# site_template: the phone trip page

A single-file, offline-first page for a trip in progress: a swipe deck of day pages (Trip), a currency
calculator and a shared ledger with settle-up (Money), and driver cards, phrases, emergency numbers and
bookings (Kit). Members and visitors unlock it with a PIN; the server holds the PINs.

```bash
tripforge site init trips/<slug>/site --brief trips/<slug>/brief.yaml   # copies this folder, writes the trip modules
# fill the TODOs in trips/<slug>/site/src/js/03-data-trip.js and 04-data-kit.js
tripforge site build trips/<slug>/site                                   # src/ -> index.html, gated on node --check
tripforge site check trips/<slug>/site                                   # stale build or private data -> exit 1
```

`site init` reads the usual brief keys (`from`, `home_city`, `people`, `start`, `stops`, `currency`) and `out/plan.json`
(dates, stops, picked flights, ground legs, top stay, FX rate) plus two optional keys:

```yaml
site:
  title: My Trip            # default: plan title, then destination
  base: /my-trip/           # URL prefix; default /<title slug>/
  tz: Region/City           # destination IANA zone; event offsets are computed from it
  home_tz: Region/City
  travellers: [Name, Name]  # ledger payers; default: "TODO person N" x people
  local_currency: XXX       # default: the plan's single FX currency
  voice: {lang: xx, name: Language}
  theme: plain
private_patterns: ["regex", "..."]   # names, refs, PINs; site check fails on any hit in index.html or data/*.json
```

Only two files change per trip: `src/js/03-data-trip.js` and `src/js/04-data-kit.js`. Everything else is
generic. In this folder they exist as `*.example.js` with a made-up trip, so the bare template builds.

## Layout

```
src/index.html        shell: header clocks, three sections, nav, <!-- @css --> / <!-- @js --> slots, __BASE__ / __TITLE__
src/ORDER.txt         concatenation order; a module not listed is not shipped; NAME falls back to NAME.example.js
src/styles/*.css      one file per visual concern, cascade order; 90-themes holds decoration + PG filter only
src/js/*.js           plain scripts sharing one global scope, dependency order (no ES modules: one request, offline day one)
tools/build.py        src -> index.html; --check fails if index.html is stale; node --check on the inlined script
tools/merge_plans.py  research/*.json -> data/plans.json (validated, private-pattern gated)
tools/deploy.sh       build, privacy gate, SW bump, copy + install -m 644 (env: DEPLOY_HOST, DEPLOY_ROOT)
lock/index.html       public PIN page (served without the cookie); __TITLE__ / __DATES__ / __CITIES__
server/tripledger.py  PIN gate + ledger API, stdlib only, loopback only, configured by env
sw.js                 network-first service worker; cache name trip-vN, bumped every deploy
data/                 plans.json, flights.json (optional, server-polled live status)
img/                  <key>.jpg day photos, stays/<prefix>-<n>.jpg stay photos (not in the template)
```

## Modules

| module | does |
|---|---|
| 01-data | `ROLE` (cached from `api/me`), `esc()` |
| 02-themes | `THEMES` registry, `applyTheme()`, `stickers()`, theme picker; `VISITOR_THEME` |
| 03-data-trip | TRIP-SPECIFIC: `TRIP`, icons `I`, `ICAO`, link helpers, `EVENTS`, `CRED`, `STAYS`, `DAYS` |
| 04-data-kit | TRIP-SPECIFIC: `PHRASES`, `TODO`, `PACK`, `KIT` |
| 04b-shell | fills the shell from the data: title, clocks, first-page pills, weather boxes, currency and payer pickers, fares, budget, driver cards, emergency, bookings (members only), tips, footer |
| 05-tabs | `go()` between Trip / Money / Kit |
| 06-clock-progress | dual clock, countdown, day N of M, `day0()` |
| 07-ticket | next-flight ticket |
| 08-live-flight-status | `data/flights.json` -> `[data-fl]` strips |
| 09-today | GPS, `km()`, `eta()`, `todayIdx()`, distances on plan options |
| 10-weather | Open-Meteo now + 16-day per city, `dayWx()` |
| 11-daily-plan | `data/plans.json` -> slots and options, PG filter, `loadPlans()` |
| 12-day-deck | day pages, slips, strip, page-turn, `specialHtml()`, `speak()`, `cp()`, `toast()` |
| 13-rate-calculator | FX (Frankfurter, then ExchangeRate-API), calculator, ÷N key |
| 14-role | visitor freeze of Money, PIN pad, lock |
| 14b-settle | `settle(balances)`: minimum-transfer settle-up (zero-sum-subset bitmask DP) |
| 15-ledger | ledger client, balances, settle-up, categories, budget drift, share text |
| 16-phrases, 17-checklists, 19-boot | phrases with TTS, checkbox lists in localStorage, timers + service worker |

## TRIP

| field | meaning |
|---|---|
| `title`, `dates` | header and lock page |
| `tagline` | first-page headline before the trip ("A first. B last.") |
| `hello` | progress pill during the trip |
| `tz`, `tzLabel` | destination IANA zone and its clock label |
| `homeTz`, `homeLabel` | home zone and label |
| `day0` | local date of `DAYS[0]` (or a full ISO datetime with offset) |
| `depart`, `back` | first take-off and last landing, ISO with offset; bound the progress bar |
| `planned` | date planning started; the countdown bar runs from here to `depart` |
| `home` | `{code, city}`: the Runway strip and directions |
| `airports` | code -> directions query for the ticket's "Directions to" |
| `cur` | `{here, home, symHere, symHome, locale, rate, quick}`; `rate` = home units per 1 local unit, used until FX loads |
| `people` | `{initial: name}`; every ledger entry splits equally across all of them |
| `voice` | `{lang, name}`: speechSynthesis voice prefix and Google Translate source |
| `cities` | `[{n, la, lo, typ}]`: weather boxes; `typ` shows until the forecast is in range |
| `cover` | image key for the first page, `img/<cover>.jpg`; empty hides the photo |
| `budget` | `{each, lines:[[label, amount]], note}` in home currency; `each` drives the drift bar |
| `defaultTheme` | member theme when nothing is saved |
| `ledgerKey` | localStorage key for the cached ledger; unique per trip |

## EVENTS

Ordered by `t`. Feeds the next-flight ticket and the "N of M booked" pill (kinds `fly` and `stay`).

| field | kinds | meaning |
|---|---|---|
| `t` | all | ISO start with the local offset of where it happens |
| `kind` | all | `fly`, `stay`, `road` |
| `st` | all | `ok` booked, `open` to book |
| `name`, `note` | all | label and one practical line |
| `from`, `to`, `fc`, `tc`, `dep`, `arr`, `dur` | fly | codes, city names, local times, duration |
| `place`, `until`, `th`, `en` | stay | where, check-out ISO, address in the local script and in English |
| `from`, `to` | road | place names |

## STAYS

Key -> stay. Aliases are fine (`STAYS.b = STAYS.a` for a two-part stay in one place); driver cards dedupe by object.

| field | meaning |
|---|---|
| `name`, `sub` | slip title and line |
| `st` | `ok` / `open` |
| `ref` | booking ref; rendered for members only |
| `book`, `site` | listing link and its label |
| `pics`, `img` | photo count and file prefix: `img/stays/<img||key>-1..pics.jpg`. Set `img` so a renamed key does not orphan the files |
| `addr`, `q` | address line; directions query (an address or `lat,lon`) |
| `th` | address in the local script, spoken and copied for drivers |
| `cap` | driver card caption ("Town, 10 to 12 Mar") |

## DAYS

One per local day starting at `TRIP.day0`.

| field | meaning |
|---|---|
| `d`, `w` | day of month and weekday label |
| `where` | place line on the page; `city` overrides the weather city when `where` is a route ("A → Home") |
| `img` | day photo key (`img/<img>.jpg`, credit `CRED[img]`); omit for a photoless page |
| `h`, `p` | headline and one paragraph |
| `sleep` | STAYS key; omit on the last day and set `sleepNote` ("Home, 21:00") |
| `move` | slips before the stay: `{kind:'fly', from, to, dep, arr, name, st, ref, sub, q}` or `{kind:'taxi', name, sub, st, q}` |
| `opts` | free-text choices shown when `plans.json` has nothing for the day |
| `special` | `{h, items:[{n, why, map?, adult?}]}`: one extra block (a countdown, a festival); `adult` hides under PG themes |
| `go` | `[{n, la, lo}]`: anchor spots for the day; seed for research briefs, not rendered |

Body order on a day page is fixed: move slips, stay slip, special, plan.

## KIT (04-data-kit)

`PHRASES` `[[local, pronunciation, meaning]]`, `TODO` (Before we fly, things with a deadline) and `PACK`
are string lists. `KIT` holds `airportCard {cap, say:[[local name, label]]}`, `sos [[name, note, tel]]`,
`hospitals [[label, maps query]]`, `fares {unit, rows:[[leg, range]], note}`, `bookings [{t, u, sub, ref}]`
(members only), `tips`, `foot`. Each fact lives in one place: a deadline in `TODO` is not repeated in tips.

## data/plans.json

Written by `tools/merge_plans.py research/ [--bbox S,W,N,E] [--private file] [--diet-label Veg]`. Input, one file per city:

```
{"place": "...", "days": [{"date": "YYYY-MM-DD", "title": "...", "tips": ["..."],
  "slots": [{"when": "morning|afternoon|sunset|dinner|night|late", "label": "...",
    "options": [{"name", "kind": "party|food|sea|sight|market|chill|move", "why", "cost", "hours",
                 "lat", "lon", "diet", "links": [{"t", "u"}], "source"}]}]}],
 "sources": ["https://..."]}
```

Output: `{updated, cities, sources, dietLabel, note?, days: {date: {title, tips, slots: [{w, l, o: [{n, k, why, cost, hrs,
la, lo, diet?, links}]}]}}}`. Options without coordinates, outside the bbox, or with non-https links are dropped; at most
3 options per slot and 4 links per option. Update it without a redeploy: copy the file, the page refetches hourly.

## Ledger entries

`{id, what, amt, cur, who, cat, ts, on?, est?, edited?}`. `who` is a `TRIP.people` initial, `cur` one of the two trip
currencies, `cat` one of travel, stay, food, party, leisure, shopping, other. `ts`/`on` are epoch ms (`on` backdates).
`est` marks a guess until edited. `what` may end in ` · <payment app>`, shown as "via". Ids match `[A-Za-z0-9_-]{4,40}`,
so seeded entries ("seed-flight-1") stay editable.

## Themes

Each entry in `THEMES` (02-themes.js) has `name`, `accent [--mari, --mari-ink]`, `deco` (up to 4 glyphs tiled at 10%
behind everything), `stk` (up to 3 glyphs on each photo) and `pg` (drops `kind:party` options, `late` slots and `.adult`
blocks). Selection: visitor -> `VISITOR_THEME`, not overridable; else `?theme=`, then the saved choice, then
`TRIP.defaultTheme`. Adding a theme is one line.

## Roles

| role | unlocks with | cookie value | sees |
|---|---|---|---|
| member | `TRIP_PIN` | `TRIP_TOKEN` | everything, refs, ledger, theme picker |
| visitor | `TRIP_PIN_RO` | `TRIP_TOKEN_RO` | Trip and Kit under the visitor theme; no refs, no bookings, no Money; `api/ledger` 403 |

`POST api/unlock` checks the PIN in constant time, rate-limits per IP (6 tries / 10 min) and sets `trip=<token>`,
HttpOnly, Secure, SameSite=Lax, path `COOKIE_PATH`. The page never sees a token. `api/me` returns the role; the page
re-checks it on every load. `api/logout` clears the cookie. Without `TRIP_PIN` + `TRIP_TOKEN` every request is refused.

## Deploy recipe

Backend (once): copy `server/tripledger.py` to `/opt/tripledger/`, run it as its own user under systemd with an
EnvironmentFile (`install -m 600 -o root -g root env.file /etc/tripledger.env`) holding `TRIP_PIN`, `TRIP_TOKEN`,
`TRIP_PIN_RO`, `TRIP_TOKEN_RO` (tokens: `python3 -c 'import secrets;print(secrets.token_urlsafe(24))'`),
`COOKIE_PATH=/my-trip`, `LEDGER_PEOPLE=ASK`, `LEDGER_CURRENCIES=EUR,USD`. It binds 127.0.0.1 only.

Caddy, inside the site block (the regex lists both tokens; rotate = edit env + regex, restart both):

```
redir /my-trip /my-trip/
route /my-trip/* {          # route keeps this order; bare handle blocks would be re-sorted by Caddy
	handle_path /my-trip/api/* {
		reverse_proxy 127.0.0.1:8765
	}
	@locked {
		not path /my-trip/lock/*
		not header_regexp Cookie (^|;\s*)trip=(TOKEN_MEMBER|TOKEN_VISITOR)(;|$)
	}
	handle @locked {
		rewrite * /my-trip/lock/index.html
		root * /var/www
		file_server
	}
	handle_path /my-trip/* {
		root * /var/www/my-trip
		header /sw.js Cache-Control no-cache
		file_server
	}
}
```

Apply Caddy changes with `systemctl restart caddy` (a reload needs the admin API, which hardened setups turn off).

Every page deploy: `tools/deploy.sh` builds (node --check), greps for private patterns, bumps `trip-vN` in `sw.js`,
copies to a temp dir on the host and `install -D -m 644`s each file into place. Then open the page at a phone
viewport and read the console before calling it done. Data-only change: copy `data/plans.json`, no build.
