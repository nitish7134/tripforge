/* ---------- rate + calculator: TRIP.cur.here <-> TRIP.cur.home. RATE = home units per 1 local unit. ---------- */
const CH=TRIP.cur.here,CO=TRIP.cur.home,SYM={[CH]:TRIP.cur.symHere,[CO]:TRIP.cur.symHome},LOC=TRIP.cur.locale;
let RATE=+(localStorage.getItem('rate-'+CH+CO)||TRIP.cur.rate),rateAt=localStorage.getItem('rateAt-'+CH+CO);
let A='0',mode=CH;
function rateLine(src){const el=document.getElementById('rate-line');if(!el)return;el.textContent=`1 ${CH} = ${SYM[CO]}${RATE.toFixed(3)} · ${src}`}
rateLine(rateAt?'cached '+rateAt:'default');
const FX_SRC=[[`https://api.frankfurter.dev/v1/latest?base=${CH}&symbols=${CO}`,r=>[r.rates&&r.rates[CO],r.date,'ECB']],
              [`https://open.er-api.com/v6/latest/${CH}`,r=>[r.rates&&r.rates[CO],(r.time_last_update_utc||'').slice(5,16),'ExchangeRate-API']]];
async function fx(){if(CH===CO)return;for(const [u,pick] of FX_SRC){try{const r=await fetch(u,{cache:'no-store'});if(!r.ok)continue;const [v,d,src]=pick(await r.json());
 if(v){RATE=+v;rateAt=d;localStorage.setItem('rate-'+CH+CO,v);localStorage.setItem('rateAt-'+CH+CO,d);rateLine(`live ${src}, ${d}`);show();renderL();return}}catch(e){}}
 rateLine(rateAt?'offline, cached '+rateAt:'offline, approximate')}
fx();
const other=c=>c===CH?CO:CH;
function show(){if(!document.getElementById('val-a'))return;const a=parseFloat(A)||0;const b=mode===CH?a*RATE:a/RATE;
 document.getElementById('cur-a').textContent=mode;document.getElementById('cur-b').textContent=other(mode);
 document.getElementById('val-a').innerHTML=`<span class="sym">${SYM[mode]}</span>${fmtN(A)}`;document.getElementById('val-b').innerHTML=`<span class="sym">${SYM[other(mode)]}</span>${fmtN(b.toFixed(b<100?2:0))}`}
function fmtN(s){s=String(s);const [i,f]=s.split('.');return (+i).toLocaleString(LOC)+(f!==undefined?'.'+f:'')}
function k(x){if(x==='C')A='0';else if(x==='⌫')A=A.length>1?A.slice(0,-1):'0';else if(x==='split')A=String(+((parseFloat(A)||0)/NP).toFixed(2));else if(x==='.'){if(!A.includes('.'))A+='.'}else{A=A==='0'?x:A+x;if(A.length>10)A=A.slice(0,10)}show();if(navigator.vibrate)navigator.vibrate(4)}
function setA(v){A=String(v);mode=CH;show()}
function swap(){const a=parseFloat(A)||0;A=String(+((mode===CH?a*RATE:a/RATE).toFixed(2)));mode=other(mode);show()}
function addFromCalc(){document.getElementById('l-amt').value=parseFloat(A)||'';document.getElementById('l-cur').value=mode;document.getElementById('l-what').focus();document.getElementById('l-what').scrollIntoView({behavior:'smooth',block:'center'})}
show();
