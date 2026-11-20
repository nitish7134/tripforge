/* ---------- sections: every DATA.sections entry loads data/<id>.json on its own, so a slow or failing one never blocks the rest ---------- */
const SEC_TTL=8e3;
const secFmt=(v)=>typeof v==='number'?v.toLocaleString('en-IN'):esc(v);
function secKv(o,skip){return Object.entries(o).filter(([k,v])=>!skip.includes(k)&&v!==null&&v!==''&&typeof v!=='object').map(([k,v])=>`<div class="fr"><span></span>${esc(k)}: ${secFmt(v)}</div>`).join('')}
function secAuto(v,depth=0){ /* tolerant fallback for any JSON shape: lists become cards, objects become lines */
 if(Array.isArray(v))return v.map(x=>typeof x==='object'&&x?`<div class="panel fp">${secAuto(x,depth+1)}</div>`:`<div class="fr"><span>•</span>${esc(x)}</div>`).join('');
 if(v&&typeof v==='object'){const head=v.title||v.name||v.h||v.label||v.where||v.date||v.day;
  const rest=Object.entries(v).map(([k,x])=>{if(x===null||x==='')return'';if(typeof x==='object')return`<details class="fold"${depth<1?' open':''}><summary>${esc(k)}</summary>${secAuto(x,depth+1)}</details>`;
   return(x===head)?'':`<div class="fr"><span></span>${esc(k)}: ${/^https?:\/\//.test(x)?`<a href="${esc(x)}" target="_blank" rel="noopener">link</a>`:secFmt(x)}</div>`}).join('');
  return(head?`<div class="kv"><b>${esc(head)}</b></div>`:'')+rest}
 return esc(v)}
function secFlights(j){
 const sym=j.sym||TRIP.sym||'';const opts=j.options||[];
 return opts.map(o=>`<div class="panel fp${o.id===j.best?' best':''}">
  <div class="kv"><b>${esc(o.label)}</b><span>${o.fails?`<span class="pill bad">${o.fails} rule${o.fails>1?'s':''} broken</span>`:'<span class="pill ok">rules met</span>'}${o.warns?` <span class="pill open">${o.warns} close call</span>`:''}</span></div>
  ${(o.legs||[]).map(l=>`<div class="fl"><small>${esc(l.who)} · ${esc(l.dir)}</small><div><b>${esc(l.flight)}</b> ${esc(l.from)} → ${esc(l.to)} · ${esc(l.depL)} → ${esc(l.arrL)}${(l.verified??o.verified??j.verified)===true?'':' '+secEst().replace('>est<','>unverified<')}${l.price?` · <span class="num">${esc(sym)}${secFmt(l.price)}</span>`:''}</div></div>`).join('')}
  ${(o.results||[]).map(r=>`<div class="fr ${r.ok?'ok':r.soft?'warn':'bad'}"><span>${r.ok?'✓':r.soft?'!':'✗'}</span>${esc(r.label)}: ${esc(r.detail)}</div>`).join('')}
  <div class="kv"><span class="muted">Total, all legs${o.id===j.best?' · best pick':''}</span><b class="num">${esc(sym)}${secFmt(o.total||0)}</b></div>
  ${o.note?`<p class="muted">${esc(o.note)}</p>`:''}</div>`).join('')+(j.note?`<p class="muted">${esc(j.note)}</p>`:'')}

const secLink=(u,t)=>/^https?:\/\//.test(u||'')?` <a href="${esc(u)}" target="_blank" rel="noopener">${esc(t||'link')}</a>`:'';
const secMoney=o=>Object.entries(o).filter(([k,v])=>/^(est_|price_|total_)?[a-z]{3}$/.test(k)&&/^(inr|thb|usd|eur|gbp|aed|sgd|myr|idr|vnd|jpy)$/.test(k.slice(-3))&&v).map(([k,v])=>k.slice(-3).toUpperCase()+' '+esc(v)).join(' · ');
const secEst=(t)=>`<span class="pill open" title="Not verified for these dates">est</span>`;
function secItinerary(j){ /* kind "itinerary": verdict, days[].blocks, stays, transfer, rules, visa, budget; anything marked unverified shows an est pill */
 const L=(a)=>(a||[]).map(x=>`<div class="fr"><span>•</span>${esc(x)}</div>`).join('');
 const fold=(h,b,open)=>b?`<details class="fold${h.startsWith('Stays')?' est-stays':''}"${open?' open':''}><summary>${esc(h)}</summary><div class="panel">${b}</div></details>`:'';
 let o='';
 if(j.verdict)o+=`<div class="panel fp best"><div class="kv"><b>${esc((j.verdict.pair||[]).join(' + '))}</b><span class="pill ok">pick</span></div><p>${esc(j.verdict.split)}</p>${L(j.verdict.why)}${j.verdict.note_flights?`<p class="muted">${esc(j.verdict.note_flights)}</p>`:''}</div>`;
 o+=`<div class="panel"><div class="kv"><span>${secEst()} <b>Estimates, not quotes.</b></span></div><p class="muted">Prices, opening hours and fares are not verified for these dates. Check before booking.${j.fx_assumption?' '+esc(j.fx_assumption)+'.':''}</p></div>`;
 (j.days||[]).forEach(d=>{o+=`<h2>${esc(d.label||d.date)}</h2><div class="panel">${d.assumption?`<p class="muted">${secEst()} ${esc(d.assumption)}</p>`:''}`+(d.blocks||[]).map(b=>`<div class="fl"><small>${esc(b.time)}${b.place?' · '+esc(b.place):''}</small><div><b>${esc(b.title)}</b>${secLink(b.link,'more')}</div>${b.why?`<div class="muted">${esc(b.why)}</div>`:''}</div>`).join('')+'</div>'});
 if((j.stays||[]).length&&!window.SEC_STAYS_OK)o+=fold('Stays (estimates)',(j.stays).map(st=>`<div class="kv"><b>${esc(st.place)}</b></div>${st.note?`<p class="muted">${esc(st.note)}</p>`:''}`+(st.options||[]).map(x=>`<div class="fl"><small>${esc(x.area)}</small><div><b>${esc(x.name)}</b> ${secEst()} ${secMoney(x)} a night${secLink(x.link,'site')}</div></div>`).join('')).join(''));
 if(j.transfer)o+=fold('Getting between the cities',`<p><b>${esc(j.transfer.recommended)}</b></p>`+(j.transfer.options||[]).map(x=>`<div class="fl"><small>${esc(x.mode)} · ${esc(x.duration||'')}</small><div>${esc(x.carriers||'')} ${secEst()} ${esc(x.price_inr_estimate||secMoney(x))}${secLink(x.source,'source')}</div><div class="muted">${esc(x.status||'')}</div></div>`).join('')+Object.entries(j.transfer.airport_transfers||{}).map(([k,v])=>`<div class="fr"><span>•</span>${esc(k.replace('_',' '))}: ${esc(v)}</div>`).join(''));
 if(j.getting_around)o+=fold('Getting around',Object.entries(j.getting_around).filter(([k,v])=>Array.isArray(v)&&k!=='sources').map(([k,v])=>`<div class="kv"><b>${esc(k)}</b></div>${L(v)}`).join(''));
 if((j.rules_to_flag||[]).length)o+=fold('Rules to know',L(j.rules_to_flag));
 if(j.visa)o+=fold('Visa and arrival card',`<p>${esc(j.visa.summary)}</p>${secLink(j.visa.official_source,'TDAC portal')}<p class="muted">${esc(j.visa.status||'')}</p>`);
 if(j.budget)o+=fold('Budget (both, 3 nights, no international flights)',`<p class="muted">${secEst()} ${esc(j.budget.currency_note||'')}</p>`+(j.budget.lines||[]).map(l=>`<div class="kv"><span>${esc(l.item)}</span><b class="num">${secMoney(l)}</b></div>`).join('')+`<div class="kv"><b>Total</b><b class="num">${secMoney({total_inr:j.budget.total_inr})}</b></div><p class="muted">${esc(j.budget.excluded_but_needed||'')}</p>`);
 if((j.unverified||[]).length)o+=fold('Still unverified',L(j.unverified));
 if((j.assumptions||[]).length)o+=fold('Assumptions',L(j.assumptions));
 return o}

function secStays(j){ /* kind "stays": per place a top pick and runner-up (or options[]); each listing links straight to the listing; unverified unless verified:true */
 window.SEC_STAYS_OK=true;document.querySelectorAll('.est-stays').forEach(e=>e.remove());
 const places=j.places||j.stays||(Array.isArray(j)?j:[j]);
 const card=(x,tag)=>{if(!x||typeof x!=='object')return'';const url=x.url||x.link||x.listing_url||x.listing;const name=x.name||x.title||'Listing';
  const ver=(x.verified??j.verified)===true;const money=secMoney(x)||(x.price?esc(x.price):'');
  return`<div class="fl"><small>${esc(tag)}${x.area?' · '+esc(x.area):''}${x.type?' · '+esc(x.type):''}</small><div><b>${/^https?:\/\//.test(url||'')?`<a href="${esc(url)}" target="_blank" rel="noopener">${esc(name)}</a>`:esc(name)}</b> ${ver?'':secEst().replace('>est<','>unverified<')}${money?' · '+money+' a night':''}${x.rating?' · ★'+esc(x.rating):''}${x.reviews?' ('+esc(x.reviews)+')':''}</div>${x.why||x.note?`<div class="muted">${esc(x.why||x.note)}</div>`:''}${x.checked_at?`<div class="muted">checked ${esc(x.checked_at)}</div>`:''}</div>`};
 return places.map(pl=>`<div class="panel fp"><div class="kv"><b>${esc(pl.place||pl.name||'')}</b><span class="muted">${esc(pl.dates||pl.nights||'')}</span></div>${card(pl.top_pick||pl.top||pl.pick,'Top pick')}${card(pl.runner_up||pl.runnerup||pl.second,'Runner-up')}${(pl.options||[]).map(o=>card(o,'Option')).join('')}${pl.note?`<p class="muted">${esc(pl.note)}</p>`:''}</div>`).join('')+(j.note?`<p class="muted">${esc(j.note)}</p>`:'')}
const SEC_RENDER={flightPlan:secFlights,itinerary:secItinerary,stays:secStays};
async function secLoad(s,box){
 const body=box.querySelector('.sb'),ac=new AbortController(),to=setTimeout(()=>ac.abort(),SEC_TTL);
 try{const r=await fetch(`data/${s.id}.json`,{cache:'no-store',signal:ac.signal});
  if(r.status===404){if(!box.dataset.ok)body.innerHTML='<p class="muted">Coming soon. This part is still being researched.</p>';return}
  if(!r.ok)throw new Error(r.status);
  const txt=await r.text();if(txt===box.dataset.ok)return;   // unchanged: no re-render
  const j=JSON.parse(txt);body.innerHTML=(SEC_RENDER[s.kind]||secAuto)(j)||'<p class="muted">Empty.</p>';box.dataset.ok=txt}
 catch(e){if(!box.dataset.ok)body.innerHTML='<p class="muted">Could not load this part just now. It will retry.</p>'}
 finally{clearTimeout(to)}}
function startSections(){
 const host=document.getElementById('sections');if(!host)return;
 (DATA.sections||[]).forEach(s=>{const box=document.createElement('div');box.id='sec-'+s.id;
  box.innerHTML=`<h2>${esc(s.title||s.id)}</h2><div class="sb"><p class="muted">Loading…</p></div>`;host.appendChild(box);
  secLoad(s,box);setInterval(()=>secLoad(s,box),(s.every||300)*1e3)});   // each section: its own request and its own refresh clock
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')(DATA.sections||[]).forEach(s=>secLoad(s,document.getElementById('sec-'+s.id)))})}
startSections();
