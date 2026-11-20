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
 const sym=TRIP.sym||'';const opts=j.options||[];
 return opts.map(o=>`<div class="panel fp${o.id===j.best?' best':''}">
  <div class="kv"><b>${esc(o.label)}</b><span>${o.fails?`<span class="pill bad">${o.fails} rule${o.fails>1?'s':''} broken</span>`:'<span class="pill ok">rules met</span>'}${o.warns?` <span class="pill open">${o.warns} close call</span>`:''}</span></div>
  ${(o.legs||[]).map(l=>`<div class="fl"><small>${esc(l.who)} · ${esc(l.dir)}</small><div><b>${esc(l.flight)}</b> ${esc(l.from)} → ${esc(l.to)} · ${esc(l.depL)} → ${esc(l.arrL)}${l.price?` · <span class="num">${esc(sym)}${secFmt(l.price)}</span>`:''}</div></div>`).join('')}
  ${(o.results||[]).map(r=>`<div class="fr ${r.ok?'ok':r.soft?'warn':'bad'}"><span>${r.ok?'✓':r.soft?'!':'✗'}</span>${esc(r.label)}: ${esc(r.detail)}</div>`).join('')}
  <div class="kv"><span class="muted">Total, all legs${o.id===j.best?' · best pick':''}</span><b class="num">${esc(sym)}${secFmt(o.total||0)}</b></div>
  ${o.note?`<p class="muted">${esc(o.note)}</p>`:''}</div>`).join('')+(j.note?`<p class="muted">${esc(j.note)}</p>`:'')}
const SEC_RENDER={flightPlan:secFlights};
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
