/* ---------- runtime config: TRIP and DATA are injected by the generator from trip.json ---------- */
/* TRIP  = {slug,name,home,start,end,tz,homeTz,cur,sym,people:[{k,n}],split,budget,defaultTheme,t0,t1,built,
            features:{fx,phrases,visitorRole,flights}, fxBase, fxQuote, speakLang}
   DATA  = {events,stays,days,tix,cred,todo,pack,phrases,cities,typical,emergency,...} (see site/SCHEMA.md) */
const TZ=TRIP.tz;
let ROLE=localStorage.getItem('role')||'member';
const I={radar:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 12l6-6"/></svg>',pin:'<svg viewBox="0 0 24 24"><path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>',car:'<svg viewBox="0 0 24 24"><path d="M5 16l1.5-5h11L19 16M3 16h18v3H3zM7 19v2M17 19v2"/></svg>',bed:'<svg viewBox="0 0 24 24"><path d="M3 18v-7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v7M3 18h18M7 9V7h4v2"/></svg>',say:'<svg viewBox="0 0 24 24"><path d="M11 5L6 9H3v6h3l5 4zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>'};
const EVENTS=DATA.events||[],STAYS=DATA.stays||{},DAYS=DATA.days||[],TIX=DATA.tix||{},CRED=DATA.cred||{},PHRASES=DATA.phrases||[],TODO=DATA.todo||[],PACK=DATA.pack||[];
const ICAO=DATA.icao||{};
function fkey(name){const m=name.match(/\b([A-Z0-9]{2})\s?(\d{2,4})\b/);return m?m[1]+m[2]:name}
function live(name){const m=name.match(/\b([A-Z0-9]{2})\s?(\d{2,4})\b/);return m?`https://www.flightradar24.com/data/flights/${(m[1]+m[2]).toLowerCase()}`:'https://www.flightradar24.com/'}
const dir=q=>'https://www.google.com/maps/dir/?api=1&travelmode=driving&destination='+encodeURIComponent(q);
const fmtMoney=(v,sym)=>`${sym||TRIP.sym}${Math.round(v).toLocaleString(TRIP.locale||'en-IN')}`;
