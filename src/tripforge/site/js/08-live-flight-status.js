/* ---------- live flight status (server-fetched, see data/flights.json) ---------- */
let LIVE={};
async function liveFlights(){try{const r=await fetch('data/flights.json',{cache:'no-store'});if(!r.ok)return;LIVE=await r.json()}catch(e){return}
 document.querySelectorAll('[data-fl]').forEach(el=>{const f=LIVE.flights&&LIVE.flights[el.dataset.fl];if(!f)return;
  const late=f.dep_delay_min>10;const parts=[];
  parts.push(`<span><small>Status</small><br><b class="${late?'late':'ontime'}">${f.status||'scheduled'}</b></span>`);
  if(f.dep_est)parts.push(`<span><small>Departs</small><br><b class="${late?'late':''}">${f.dep_est}</b>${late?` <small>+${f.dep_delay_min} min</small>`:''}</span>`);
  if(f.arr_est)parts.push(`<span><small>Arrives</small><br><b>${f.arr_est}</b></span>`);
  if(f.terminal)parts.push(`<span><small>Terminal</small><br><b>${f.terminal}</b></span>`);
  if(f.gate)parts.push(`<span><small>Gate</small><br><b>${f.gate}</b></span>`);
  if(f.belt)parts.push(`<span><small>Belt</small><br><b>${f.belt}</b></span>`);
  el.innerHTML=`<div class="lv">${parts.join('')}<span style="flex-basis:100%;color:var(--paper-ink-2);font-size:11.5px">${f.source||''} · updated ${f.updated||''}</span></div>`})}

