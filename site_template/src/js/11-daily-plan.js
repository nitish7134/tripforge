/* ---------- daily plan (data/plans.json, refreshed without a redeploy) ---------- */
const WHEN_L={morning:'Morning',afternoon:'Afternoon',sunset:'Sunset',dinner:'Dinner',night:'Night',late:'Late',anytime:'Any time'};
function dateOf(i){const d=new Date(TRIP.day0.slice(0,10)+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+i);return d.toISOString().slice(0,10)}
function slotNow(){const hr=+new Intl.DateTimeFormat('en-GB',{hour:'2-digit',hour12:false,timeZone:TZ}).format(new Date());return hr<12?'morning':hr<17?'afternoon':hr<19?'sunset':hr<21?'dinner':'night'}
function optHtml(o){const dist=POS?km(POS.la,POS.lo,o.la,o.lo):null;
 const lbl=l=>{if(/^(blog|source|link|web|site|article)$/i.test(l.t||'')){try{return new URL(l.u).hostname.replace(/^www\./,'').replace(/\.[a-z]{2,6}(\.[a-z]{2})?$/,'')}catch(e){return l.t}}return l.t};
 const seen=new Set();const links=(o.links||[]).filter(l=>{const k=lbl(l).toLowerCase();if(seen.has(k))return false;seen.add(k);return true}).map(l=>`<a class="${/instagram/i.test(l.t+l.u)?'ig':''}" href="${esc(l.u)}" target="_blank" rel="noopener">${esc(lbl(l))}</a>`).join('');
 return `<div class="pl" data-la="${o.la}" data-lo="${o.lo}"><div><span class="kd ${esc(o.k)}">${esc(o.k)}</span><b>${esc(o.n)}</b><small>${esc(o.why)}</small><small class="meta">${esc(o.cost)}${o.hrs?' · '+esc(o.hrs):''}</small>${o.diet||o.veg?`<small class="veg">${esc((PLANS&&PLANS.dietLabel)||'Diet')}: ${esc(o.diet||o.veg)}</small>`:''}<small class="dist">${dist!=null?`<span class="far">${dist<10?dist.toFixed(1):Math.round(dist)} km</span> · ${eta(dist)}`:''}</small><div class="lk">${links}</div></div><a href="https://www.google.com/maps/dir/?api=1&destination=${o.la},${o.lo}" target="_blank">Go</a></div>`}
function planHtml(date,isToday){const p0=PLANS&&PLANS.days&&PLANS.days[date];if(!p0||!p0.slots.length)return '';const now=isToday?slotNow():null;
 const p=THEME.pg?{...p0,slots:p0.slots.filter(s=>s.w!=='late').map(s=>({...s,o:s.o.filter(o=>o.k!=='party')})).filter(s=>s.o.length)}:p0;if(!p.slots.length)return '';
 return `<div class="plan">${p.slots.map(s=>`<details ${s.w===now?'open':''}><summary><em>${WHEN_L[s.w]||s.w}</em>${esc(s.l)}<small>${s.o.length} ${s.o.length===1?'option':'options'}</small></summary>${s.o.map(optHtml).join('')}</details>`).join('')}
 ${p.tips&&p.tips.length?`<details><summary><em>Tips</em>Read before you go<small>${p.tips.length}</small></summary><ul class="tips">${p.tips.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></details>`:''}
 <div class="src">${esc((PLANS&&PLANS.note)||'Sourced from guides and venue pages. Prices are the latest found; confirm at the door.')}</div></div>`}
async function loadPlans(){try{const r=await fetch('data/plans.json',{cache:'no-store'});if(!r.ok)return;const j=await r.json();if(JSON.stringify(j)!==JSON.stringify(PLANS)){PLANS=j;localStorage.setItem('plans',JSON.stringify(j));timeline()}}catch(e){}}

