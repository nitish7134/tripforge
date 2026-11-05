/* ---------- trip data: the only file besides 04-data-kit that changes per trip ----------
   EXAMPLE. Every name, code, ref and coordinate below is made up (a fictional island trip).
   `tripforge site init` writes 03-data-trip.js from brief.yaml + plan.json; it never edits this example.
   Anything still marked TODO must be filled before `tripforge site check` passes. */
const TRIP={
 title:'Vela Islands', dates:'10 – 14 Mar',
 tagline:'Port Vela first. Mirrow Bay last.',          // pre-trip headline on the first page
 hello:'Hello',                                        // shown on the progress pill during the trip
 tz:'Atlantic/Cape_Verde', tzLabel:'VEL',              // destination time zone (IANA) + clock label
 homeTz:'UTC', homeLabel:'HOME',                       // home time zone + clock label
 day0:'2027-03-10',                                    // local date of DAYS[0]
 depart:'2027-03-10T08:00:00+00:00',                   // first take-off (ISO with offset): countdown target
 back:'2027-03-14T21:00:00+00:00',                     // last landing at home: progress bar end
 planned:'2027-01-15',                                 // when planning started: countdown bar baseline
 home:{code:'ZZH',city:'Homeport'},
 airports:{ZZH:'Homeport International Airport',ZZV:'Port Vela Airport',ZZM:'Mirrow Bay Airstrip'},  // code -> directions query
 cur:{here:'EUR',home:'USD',symHere:'€',symHome:'$',locale:'en-US',rate:1.1,quick:[5,10,20,50,100]},  // rate: 1 here = rate home (fallback until FX loads)
 people:{A:'Alex',S:'Sam',K:'Kai'},                    // ledger initial -> display name; split is equal across all
 voice:{lang:'pt',name:'Portuguese'},                  // speechSynthesis + Google Translate source language
 cities:[                                              // weather boxes; a day picks its city by DAYS[].city, else DAYS[].where
  {n:'Port Vela',la:10.1,lo:-30.2,typ:'Typical mid March · 26° / 21° · dry'},
  {n:'Mirrow Bay',la:10.4,lo:-30.6,typ:'Typical mid March · 25° / 20° · windy'}],
 cover:'velacover',                                    // img/<cover>.jpg on the first page; credit in CRED
 budget:{each:900,lines:[['Flights',380],['Stays, 4 nights',260],['Meals',160],['Boats and entry fees',100]],
  note:'Split equally. "Real" is the shared ledger converted at today\'s rate.'},
 defaultTheme:'plain',
 ledgerKey:'vela-ledger-cache'                         // localStorage key; one per trip so two trip pages on one phone do not mix
};

const I={radar:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 12l6-6"/></svg>',pin:'<svg viewBox="0 0 24 24"><path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>',car:'<svg viewBox="0 0 24 24"><path d="M5 16l1.5-5h11L19 16M3 16h18v3H3zM7 19v2M17 19v2"/></svg>',bed:'<svg viewBox="0 0 24 24"><path d="M3 18v-7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v7M3 18h18M7 9V7h4v2"/></svg>',say:'<svg viewBox="0 0 24 24"><path d="M11 5L6 9H3v6h3l5 4zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>'};

/* Live status: Flightradar24 flight pages need no key. ICAO maps a 2-letter airline code to FlightAware's 3-letter one. */
const ICAO={ZV:'ZVX'};
function fkey(name){const m=name.match(/\b([A-Z0-9]{2})\s?(\d{2,4})\b/);return m?m[1]+m[2]:name}
function live(name){const m=name.match(/\b([A-Z0-9]{2})\s?(\d{2,4})\b/);return m?`https://www.flightradar24.com/data/flights/${(m[1]+m[2]).toLowerCase()}`:'https://www.flightradar24.com/'}
function fa(name){const m=name.match(/\b([A-Z0-9]{2})\s?(\d{2,4})\b/);return m?`https://www.flightaware.com/live/flight/${ICAO[m[1]]||m[1]}${m[2]}`:'#'}
const board=c=>`https://www.flightradar24.com/data/airports/${c.toLowerCase()}/departures`;
const dir=q=>'https://www.google.com/maps/dir/?api=1&travelmode=driving&destination='+encodeURIComponent(q);

const EVENTS=[ // ordered by t (ISO with the local offset of where it happens)
 {t:'2027-03-10T08:00:00+00:00',kind:'fly',from:'ZZH',to:'ZZV',fc:'Homeport',tc:'Port Vela',name:'Zephyr ZV 101',dep:'08:00',arr:'11:30',dur:'4h30',st:'ok',note:'Terminal 1. Be there by 06:00.'},
 {t:'2027-03-10T13:00:00-01:00',kind:'stay',place:'Port Vela',until:'2027-03-12T11:00:00-01:00',name:'Harbour Flat',st:'ok',th:'Apartamento do Porto, Rua Exemplo 1',en:'Harbour Flat, 1 Example Street',note:'Check-in 13:00, out 11:00.'},
 {t:'2027-03-12T10:00:00-01:00',kind:'road',from:'Port Vela',to:'Mirrow Bay',name:'Ferry, about 2h',st:'open',note:'Buy at the pier the day before.'},
 {t:'2027-03-12T14:00:00-01:00',kind:'stay',place:'Mirrow Bay',until:'2027-03-14T11:00:00-01:00',name:'Dune Hostel, private room',st:'ok',th:'Albergue das Dunas',en:'Dune Hostel, Beach Road',note:'Twin room.'},
 {t:'2027-03-14T15:00:00-01:00',kind:'fly',from:'ZZM',to:'ZZH',fc:'Mirrow Bay',tc:'Homeport',name:'Zephyr ZV 202',dep:'15:00',arr:'21:00',dur:'5h',st:'ok',note:'Be at the airstrip by 13:30.'}
];
const CRED={velacover:'Example Photographer, CC0',vela:'Example Photographer, CC0',mirrow:'Example Photographer, CC0'};  // img key -> credit line
const STAYS={ // key -> stay slip + "Show the driver" card. Photos: img/stays/<img||key>-1..pics.jpg
 vela:{name:'Harbour Flat',sub:'Port Vela · in 13:00, out 11:00 · Example Rentals',st:'ok',ref:'EXAMPLE-REF-1',book:'https://example.com/listing/1',site:'Example Rentals',pics:2,img:'vela',addr:'1 Example Street, Port Vela',q:'10.1,-30.2',th:'Apartamento do Porto, Rua Exemplo 1',cap:'Port Vela, 10 to 12 Mar'},
 mirrow:{name:'Dune Hostel, private room',sub:'Mirrow Bay · twin · Example Hostels',st:'ok',ref:'EXAMPLE-REF-2',book:'https://example.com/listing/2',site:'Example Hostels',pics:0,addr:'Beach Road, Mirrow Bay',q:'10.4,-30.6',th:'Albergue das Dunas',cap:'Mirrow Bay, 12 to 14 Mar'}
};
const DAYS=[ // one entry per local day, DAYS[0] is TRIP.day0
 {go:[{n:'Old harbour',la:10.101,lo:-30.201}],d:'10',w:'Wed',img:'vela',where:'Port Vela',h:'Land, harbour walk',p:'Land 11:30, taxi 20 min to the flat. Harbour walk at sunset.',sleep:'vela',
  move:[{kind:'fly',from:'ZZH',to:'ZZV',dep:'08:00',arr:'11:30',name:'Zephyr ZV 101',st:'ok',ref:'EXAMPLE-PNR-1',sub:'Terminal 1 · be there by 06:00',q:'Homeport International Airport'},{kind:'taxi',name:'Then: taxi to the flat',sub:'20 min · fixed fare at the rank',st:'none',q:'10.1,-30.2'}]},
 {go:[{n:'Lighthouse',la:10.12,lo:-30.25},{n:'Fish market',la:10.098,lo:-30.198}],d:'11',w:'Thu',img:'vela',where:'Port Vela',h:'Pick a day',p:'Evening: the fish market grill.',sleep:'vela',opts:['Lighthouse hike, 3 h return, free.','Boat to the sea caves, half day.']},
 {go:[{n:'Mirrow beach',la:10.401,lo:-30.601}],d:'12',w:'Fri',img:'mirrow',where:'Mirrow Bay',h:'Ferry south, beach',p:'Ferry at 10:00, in by 12:00.',sleep:'mirrow',
  move:[{kind:'taxi',name:'Ferry, Port Vela to Mirrow Bay',sub:'about 2 h · buy at the pier the day before',st:'open',q:'Port Vela ferry pier'}],
  special:{h:'Tonight',items:[{n:'Dune bonfire',why:'Free, on the beach from 21:00.',map:'10.401,-30.601'},{n:'After midnight',why:'Beach bar runs late.',adult:true}]}},
 {go:[],d:'13',w:'Sat',where:'Mirrow Bay',h:'Slow day',p:'Beach, a long lunch, an early night.',sleep:'mirrow'},
 {go:[{n:'Mirrow Bay Airstrip',la:10.41,lo:-30.62}],d:'14',w:'Sun',img:'mirrow',where:'Mirrow Bay → Homeport',city:'Mirrow Bay',h:'Fly home',p:'Check out 11:00, airstrip by 13:30.',sleepNote:'Home, 21:00',
  move:[{kind:'fly',from:'ZZM',to:'ZZH',dep:'15:00',arr:'21:00',name:'Zephyr ZV 202',st:'ok',ref:'EXAMPLE-PNR-2',sub:'Be there by 13:30',q:'Mirrow Bay Airstrip'}]}
];
