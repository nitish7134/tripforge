/* ---------- shared ledger (server API, entries editable). TRIP.split: 'equal' shows per-person balances; 'none' shows a total only. ---------- */
const SPLIT=TRIP.split||'none',NP=TRIP.people.length,NM=Object.fromEntries(TRIP.people.map(p=>[p.k,p.n]));
let who=TRIP.people[0].k,EDIT=null;
const whoBox=document.getElementById('l-who');
if(whoBox){if(SPLIT==='equal'){whoBox.innerHTML=TRIP.people.map((p,i)=>`<button data-w="${p.k}" class="${i?'':'on'}">${p.n}</button>`).join('');whoBox.querySelectorAll('button').forEach(b=>b.onclick=()=>{who=b.dataset.w;whoBox.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b))})}else whoBox.remove()}
const LK=TRIP.slug+'-ledger-cache';let L=JSON.parse(localStorage.getItem(LK)||'[]');
const API='api/ledger';const hdr=()=>({'Content-Type':'application/json'});
function inr(x,c){return (TRIP.features&&TRIP.features.fx&&c===TRIP.cur)?x*RATE:x} // value in home currency
const HS=TRIP.homeSym||TRIP.sym;
function note(m){const el=document.getElementById('keynote');if(el)el.textContent=m}
async function syncLedger(loud){if(ROLE==='visitor')return;
 try{const r=await fetch(API,{headers:hdr(),cache:'no-store'});if(r.status===403){note('Locked. Reload and enter the PIN again.');return}
  const d=await r.json();L=d.entries||[];localStorage.setItem(LK,JSON.stringify(L));if(EDIT&&!L.some(x=>x.id===EDIT))cancelEdit();note('Shared ledger, synced '+new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})+'. Everyone sees the same list. Tap an entry to fix it.');renderL()}
 catch(e){note('Offline: showing the last synced copy.');if(loud)toast('Offline, showing cached ledger');renderL()}}
function renderL(){const el=document.getElementById('ledger');if(!el)return;
 el.innerHTML=L.map(e=>`<div class="item${EDIT===e.id?' editing':''}" onclick="editL('${e.id}')"><div>${e.what||'Spend'}${e.est?' <span class="pill" style="padding:1px 7px;font-size:10.5px">est</span>':''}<small>${SPLIT==='equal'?(NM[e.who]||e.who)+' paid · ':''}${new Date(e.ts).toLocaleDateString('en-GB',{day:'numeric',month:'short'})}${e.edited?' · edited':''}</small></div><b class="num">${SYM[e.cur]||TRIP.sym}${(+e.amt).toLocaleString(TRIP.locale||'en-IN')}</b><button class="x" aria-label="remove" onclick="event.stopPropagation();rmL('${e.id}')">✕</button></div>`).join('')||'<p class="muted">No shared spends yet.</p>';
 const paid=Object.fromEntries(TRIP.people.map(p=>[p.k,0]));let tot=0;L.forEach(e=>{const v=inr(+e.amt,e.cur);paid[e.who]=(paid[e.who]||0)+v;tot+=v});
 const bal=document.getElementById('bal');
 if(SPLIT==='equal'){const share=tot/NP;bal.innerHTML=TRIP.people.map(p=>{const d=paid[p.k]-share;return `<div><small>${p.n} ${d>=0?'is owed':'owes'}</small><b class="num" style="color:${d>=0?'var(--ok)':'var(--open)'}">${fmtMoney(Math.abs(d),HS)}</b><small>paid ${fmtMoney(paid[p.k],HS)}</small></div>`}).join('')+`<div style="grid-column:1/-1;background:none;padding:4px 0"><small>Total shared ${fmtMoney(tot,HS)} · ${fmtMoney(share,HS)} each</small></div>`}
 else bal.innerHTML=`<div style="grid-column:1/-1"><small>Trip total so far</small><b class="num">${fmtMoney(tot,HS)}</b><small>${L.length} entr${L.length===1?'y':'ies'}</small></div>`;
 if(typeof show==='function')show();
 const EXP=TRIP.budget,real=SPLIT==='equal'?tot/NP:tot,pct=Math.min(100,Math.round(100*real/EXP)),dr=document.getElementById('drift');
 if(dr&&EXP){const lab=SPLIT==='equal'?'each':'whole trip';dr.innerHTML=`<div><small>Real, ${lab} so far</small><b class="num">${fmtMoney(real,HS)}</b></div><div><small>Expected, ${lab}</small><b class="num">${fmtMoney(EXP,HS)}</b></div><div class="bar"><i style="width:${pct}%"></i></div><div style="grid-column:1/-1"><small>${pct}% of the expected budget used · ${real<=EXP?fmtMoney(EXP-real,HS)+' headroom':fmtMoney(real-EXP,HS)+' over'}</small></div>`;const bs=document.getElementById('bud-sum');if(bs)bs.textContent=`${HS}${Math.round(real/1000)}k of ${HS}${Math.round(EXP/1000)}k${SPLIT==='equal'?' each':''}`}}
function editL(id){const e=L.find(x=>x.id===id);if(!e)return;EDIT=id;document.getElementById('l-what').value=e.what||'';document.getElementById('l-amt').value=e.amt;const c=document.getElementById('l-cur');if(c)c.value=e.cur;
 const es=document.getElementById('l-est');if(es)es.checked=!!e.est;if(SPLIT==='equal'&&whoBox){who=e.who;whoBox.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x.dataset.w===who))}
 document.getElementById('l-add').textContent='Save changes';document.getElementById('l-cancel').hidden=false;renderL();document.getElementById('l-what').scrollIntoView({behavior:'smooth',block:'center'})}
function cancelEdit(){EDIT=null;document.getElementById('l-what').value='';document.getElementById('l-amt').value='';const es=document.getElementById('l-est');if(es)es.checked=false;document.getElementById('l-add').textContent='Add to the trip ledger';document.getElementById('l-cancel').hidden=true;renderL()}
async function addLedger(){const amt=parseFloat(document.getElementById('l-amt').value);if(!amt){toast('Enter an amount');return}
 const c=document.getElementById('l-cur'),es=document.getElementById('l-est');const e={what:document.getElementById('l-what').value.trim(),amt,cur:c?c.value:TRIP.cur,who,est:!!(es&&es.checked)};const editing=EDIT;
 try{const r=await fetch(editing?API+'/'+editing:API,{method:editing?'PUT':'POST',headers:hdr(),body:JSON.stringify(e)});if(!r.ok)throw 0;
  const saved=await r.json();L=editing?L.map(x=>x.id===editing?saved:x):[saved,...L];localStorage.setItem(LK,JSON.stringify(L));
  cancelEdit();toast(editing?'Updated for everyone':'Logged for everyone');syncLedger()}catch(x){toast('Could not reach the ledger. Try again online.')}}
async function rmL(id){if(!confirm('Remove this entry for everyone?'))return;try{await fetch(API+'/'+id,{method:'DELETE',headers:hdr()});if(EDIT===id)cancelEdit();syncLedger()}catch(x){toast('Offline, try again later')}}
function shareLedger(){const paid=Object.fromEntries(TRIP.people.map(p=>[p.k,0]));let tot=0;L.forEach(e=>{const v=inr(+e.amt,e.cur);paid[e.who]=(paid[e.who]||0)+v;tot+=v});
 let txt=`${TRIP.name} trip spends\n`+L.map(e=>`• ${e.what||'Spend'}: ${SYM[e.cur]||TRIP.sym}${e.amt}${SPLIT==='equal'?' ('+(NM[e.who]||e.who)+')':''}`).join('\n')+`\n\nTotal ${fmtMoney(tot,HS)}`;
 if(SPLIT==='equal'){const sh=tot/NP;txt+=` · ${fmtMoney(sh,HS)} each\n`+TRIP.people.map(p=>`${p.n}: paid ${fmtMoney(paid[p.k],HS)}, ${paid[p.k]-sh>=0?'is owed':'owes'} ${fmtMoney(Math.abs(paid[p.k]-sh),HS)}`).join('\n')}
 if(navigator.share)navigator.share({text:txt}).catch(()=>{});else{navigator.clipboard.writeText(txt);alert('Copied')}}
if(ROLE!=='visitor'){renderL();syncLedger()}
