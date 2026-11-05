/* ---------- money pad. Two modes from TRIP.features.fx:
   fx=true : converter (foreign <-> home) with a live rate (frankfurter.dev, then open.er-api.com), cached offline
   fx=false: spend pad (amount on the left, running trip total on the right)                                  ---------- */
const FX=!!(TRIP.features&&TRIP.features.fx);
let RATE=FX?+(localStorage.getItem('rate')||TRIP.rateGuess||1):1,rateAt=localStorage.getItem('rateAt');
let A='0',mode=FX?TRIP.cur:'HOME';
const SYM={[TRIP.cur]:TRIP.sym,[TRIP.homeCur||TRIP.cur]:TRIP.homeSym||TRIP.sym};
function rateLine(src){const el=document.getElementById('rate-line');if(!el)return;el.textContent=FX?`1 ${TRIP.cur} = ${TRIP.homeSym}${RATE.toFixed(3)} · ${src}`:(TRIP.padLine||'Type a spend, tap + log.')}
rateLine(rateAt?'cached '+rateAt:'default');
const FX_SRC=FX?[[`https://api.frankfurter.dev/v1/latest?base=${TRIP.cur}&symbols=${TRIP.homeCur}`,r=>[r.rates&&r.rates[TRIP.homeCur],r.date,'ECB']],
                 [`https://open.er-api.com/v6/latest/${TRIP.cur}`,r=>[r.rates&&r.rates[TRIP.homeCur],(r.time_last_update_utc||'').slice(5,16),'ExchangeRate-API']]]:[];
async function fx(){if(!FX)return;for(const [u,pick] of FX_SRC){try{const r=await fetch(u,{cache:'no-store'});if(!r.ok)continue;const [v,d,src]=pick(await r.json());
 if(v){RATE=+v;rateAt=d;localStorage.setItem('rate',v);localStorage.setItem('rateAt',d);rateLine(`live ${src}, ${d}`);show();if(typeof renderL==='function')renderL();return}}catch(e){}}
 rateLine(rateAt?'offline, cached '+rateAt:'offline, approximate')}
fx();
function fmtN(s){s=String(s);const [i,f]=s.split('.');return (+i).toLocaleString(TRIP.locale||'en-IN')+(f!==undefined?'.'+f:'')}
function show(){const va=document.getElementById('val-a');if(!va)return;const a=parseFloat(A)||0;
 if(FX){const b=mode===TRIP.cur?a*RATE:a/RATE;const other=mode===TRIP.cur?TRIP.homeCur:TRIP.cur;document.getElementById('cur-a').textContent=mode;document.getElementById('cur-b').textContent=other;
  va.innerHTML=`<span class="sym">${SYM[mode]}</span>${fmtN(A)}`;document.getElementById('val-b').innerHTML=`<span class="sym">${SYM[other]}</span>${fmtN(b.toFixed(b<100?2:0))}`}
 else{let tot=0;try{tot=L.reduce((x,e)=>x+ +e.amt,0)}catch(e){}va.innerHTML=`<span class="sym">${TRIP.sym}</span>${fmtN(A)}`;document.getElementById('val-b').innerHTML=`<span class="sym">${TRIP.sym}</span>${fmtN(Math.round(tot))}`}}
function k(x){const n=TRIP.people.length;if(x==='C')A='0';else if(x==='⌫')A=A.length>1?A.slice(0,-1):'0';else if(x==='÷n')A=String(+((parseFloat(A)||0)/n).toFixed(2));else if(x==='k')A=String(Math.round((parseFloat(A)||0)*1000));else if(x==='.'){if(!A.includes('.'))A+='.'}else{A=A==='0'?x:A+x;if(A.length>10)A=A.slice(0,10)}show();if(navigator.vibrate)navigator.vibrate(4)}
function setA(v){A=String(v);if(FX)mode=TRIP.cur;show()}
function swap(){if(!FX)return;const a=parseFloat(A)||0;A=String(+((mode===TRIP.cur?a*RATE:a/RATE).toFixed(2)));mode=mode===TRIP.cur?TRIP.homeCur:TRIP.cur;show()}
function addFromCalc(){document.getElementById('l-amt').value=parseFloat(A)||'';const c=document.getElementById('l-cur');if(c)c.value=FX?mode:TRIP.cur;document.getElementById('l-what').focus();document.getElementById('l-what').scrollIntoView({behavior:'smooth',block:'center'})}
