# Research brief template: sourced day plans for a trip site

Copy this file to `trips/<slug>/research/BRIEF.md`, replace the two blocks marked FILL, and hand it to a research agent
(one agent per town works well). The agent writes `research/<town>.json` in the schema below plus a `NOTES.md` of what it
could not verify. `tripforge site merge-plans trips/<slug>` folds the JSONs into the page's `data/plans.json`.

## FILL: travellers and rules
Who is going (count, ages, diet, party appetite, mobility), spend ceilings per meal and per night out, how they move
(taxi apps, scooters, rail), arrival airport. Say what MUST be true (veg option at every food stop, no alcohol, kids).

## FILL: fixed facts (do not change)
One line per day with the date and its WEEKDAY (compute it from the date; a typed weekday was wrong once and shifted a whole
plan), where they sleep, flight/transfer times and check-in rules. Call out calendar-tied events (weekly markets, Sunday
parties) with the real weekday.

## Output: ONE JSON file at the path given in your task, this exact shape
{
 "place": "<town or area>",
 "days": [
  {"date":"2026-11-22","title":"short title",
   "slots":[
     {"when":"morning|afternoon|sunset|dinner|night|late","label":"what this slot is",
      "options":[
        {"name":"…","kind":"party|food|sea|sight|market|chill|move","why":"one sentence, specific, from a real source",
         "cost":"price range in the trip currency or 'free'","hours":"opening hours or best time","lat":0.0,"lon":0.0,
         "veg":"for food only: what to order for the vegetarian",
         "links":[{"t":"Instagram|Website|Maps|Reddit|Blog|Wikivoyage","u":"https://…"}],
         "source":"https://… the page that supports the claim"}
      ]}
   ],
   "tips":["2-5 practical, sourced tips for the day (taxi pricing, scooter checks, beach drinking rules, timing)"]}
 ],
 "sources":["every URL you actually read"]
}

Rules:
- Cover every date in the fixed facts; keep each day's options within reach of that night's stay. One optional long day trip is fine.
- 2-3 options per slot, genuinely different (club vs beach shack vs live music vs casino night). Night slots matter most:
  entry fee, drink prices, dress code, best night of the week, closing time, Instagram or official page. Verify each venue is still open this season (press, Instagram, Maps) before listing it.
- Food: a mix of local institutions, markets and cafes. Every food option must have a veg line.
- Coordinates: real lat/lon from OpenStreetMap/Google, 4 decimals. Never invent a place. Every option carries a "source"
  URL you read. If you cannot verify something, drop it rather than guess.
- Use Reddit (the destination's subreddits, recent threads via old.reddit.com or .rss), Wikivoyage, recent blogs,
  venue pages, Google Maps listings. No personal data. Keep "why" and "veg" under 160 characters (phone page).
- When done, write a short NOTES.md next to the JSON: what you could not verify (seasonal openings, venue closures, event dates), and the 5 best source threads.
