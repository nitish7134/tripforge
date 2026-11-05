/* ---------- weather: Open-Meteo now + 16-day forecast for each city in DATA.cities ---------- */
const CITIES=DATA.cities||[]; // [[name, lat, lon], ...]
const WC={0:'Clear',1:'Mostly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',51:'Drizzle',53:'Drizzle',55:'Drizzle',61:'Rain',63:'Rain',65:'Heavy rain',71:'Snow',73:'Snow',75:'Heavy snow',80:'Showers',81:'Showers',82:'Heavy showers',95:'Thunder',96:'Thunder',99:'Thunder'};
const WI={0:'☀',1:'🌤',2:'⛅',3:'☁',45:'🌫',51:'🌦',53:'🌦',55:'🌦',61:'🌧',63:'🌧',65:'🌧',71:'🌨',73:'🌨',75:'🌨',80:'🌦',81:'🌧',82:'⛈',95:'⛈',96:'⛈',99:'⛈'};
let WXD=JSON.parse(localStorage.getItem('wxd')||'null');
const TYP=DATA.typical||{}; // city -> one line of typical climate for the dates, used before the 16-day window
async function weather(){const box=document.getElementById('wx');if(!box||!CITIES.length)return;const cache=JSON.parse(localStorage.getItem('wx')||'null');
 const render=d=>{box.innerHTML=d.map(c=>`<div><small>${c.n}</small><span class="t num">${Math.round(c.t)}°</span><small>${WC[c.w]||'—'} · ${c.p}% rain</small></div>`).join('')};
 if(cache)render(cache.d);
 try{const out=[],days={};for(const [n,la,lo] of CITIES){const r=await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${la}&longitude=${lo}&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&forecast_days=16&timezone=${encodeURIComponent(TZ)}`);const j=await r.json();out.push({n,t:j.current.temperature_2m,w:j.current.weather_code,p:j.daily.precipitation_probability_max[0]??0});
   days[n]={};j.daily.time.forEach((t,i)=>{days[n][t]={hi:j.daily.temperature_2m_max[i],lo:j.daily.temperature_2m_min[i],p:j.daily.precipitation_probability_max[i]??0,w:j.daily.weather_code[i]}})}
 render(out);localStorage.setItem('wx',JSON.stringify({d:out,ts:Date.now()}));const wn=document.getElementById('wx-note');if(wn)wn.textContent='Live from Open-Meteo, updated '+fmtT.format(new Date())+'. Each day page shows its own forecast once the trip is inside the 16-day window.';
 const changed=JSON.stringify(days)!==JSON.stringify(WXD);WXD=days;localStorage.setItem('wxd',JSON.stringify(days));if(changed)timeline()}
 catch(e){const wn=document.getElementById('wx-note');if(cache&&wn)wn.textContent='Offline. Showing the last fetched weather.'}}
weather();
function cityOf(d){return d.wx||d.where}
function dayWx(d,date){const c=cityOf(d);const f=WXD&&WXD[c]&&WXD[c][date];
 if(!f)return TYP[c]?`<span class="ic">🌤</span><span>${TYP[c]}</span>`:'';
 return `<span class="ic">${WI[f.w]||'🌤'}</span><b>${Math.round(f.hi)}° / ${Math.round(f.lo)}°</b><span>${WC[f.w]||''} · ${f.p}% rain · ${c}</span>`}
