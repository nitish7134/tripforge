/* ---------- shared ledger (server API, entries editable). TRIP.split: 'equal' shows per-person balances, settle-up and an "I am" picker; 'none' shows a total only. TRIP.categories overrides the spend tags. ---------- */
const SPLIT=TRIP.split||'none',NP=TRIP.people.length,NM=Object.fromEntries(TRIP.people.map(p=>[p.k,p.n]));
const CATS=TRIP.categories||{travel:['✈️','Travel'],stay:['🛏','Stay'],food:['🍜','Food'],party:['🍻','Party'],leisure:['🏝','Leisure'],shopping:['🛍','Shopping'],other:['•','Other']};
let who=TRIP.people[0].k,cat=Object.keys(CATS).includes('food')?'food':Object.keys(CATS)[0],EDIT=null;
const whoBox=document.getElementById('l-who'),catBox=document.getElementById('l-cat');
if(whoBox){if(SPLIT==='equal'){whoBox.innerHTML=TRIP.people.map((p,i)=>`<button data-w="${p.k}" class="${i?'':'on'}">${p.n}</button>`).join('');whoBox.querySelectorAll('button').forEach(b=>b.onclick=()=>{who=b.dataset.w;whoBox.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b))})}else whoBox.remove()}
function drawCats(){if(!catBox)return;catBox.innerHTML=Object.entries(CATS).map(([k,[i,n]])=>`<button type="button" data-c="${k}" class="${k===cat?'on':''}">${i} ${n}</button>`).join('');catBox.querySelectorAll('button').forEach(b=>b.onclick=()=>{cat=b.dataset.c;drawCats()})}
drawCats();
const LK=TRIP.slug+'-ledger-cache',MK=TRIP.slug+'-me';let L=JSON.parse(localStorage.getItem(LK)||'[]');
const API='api/ledger';const hdr=()=>({'Content-Type':'application/json'});
function inr(x,c){return (TRIP.features&&TRIP.features.fx&&c===TRIP.cur)?x*RATE:x} // value in home currency
const HS=TRIP.homeSym||TRIP.sym;
function note(m){const el=document.getElementById('keynote');if(el)el.textContent=m}
async function syncLedger(loud){if(ROLE==='visitor')return;
 try{const r=await fetch(API,{headers:hdr(),cache:'no-store'});if(r.status===403){note('Locked. Reload and enter the PIN again.');return}
  const d=await r.json();L=d.entries||[];localStorage.setItem(LK,JSON.stringify(L));if(EDIT&&!L.some(x=>x.id===EDIT))cancelEdit();note('Shared ledger, synced '+new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})+'. Everyone sees the same list. Tap an entry to fix it.');renderL()}
 catch(e){note('Offline: showing the last synced copy.');if(loud)toast('Offline, showing cached ledger');renderL()}}
function dayKey(e){return new Date(e.on||e.ts).toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'})}
function rowHtml(e,me){const v=inr(+e.amt,e.cur),sh=v/NP;const c=CATS[e.cat]||CATS.other||['•','Other'];
 let right=`<b class="num">${fmtMoney(v,HS)}</b>`;
 if(SPLIT==='equal')right=me?`<b class="num ${e.who===me?'pos':'neg'}">${e.who===me?'lent '+fmtMoney(v-sh,HS):'owe '+fmtMoney(sh,HS)}</b>`:`<b class="num">${fmtMoney(sh,HS)} each</b>`;
 const paid=SPLIT==='equal'?`${NM[e.who]||e.who} paid ${SYM[e.cur]||TRIP.sym}${Math.round(+e.amt).toLocaleString(TRIP.locale||'en-IN')}`:`${SYM[e.cur]||TRIP.sym}${Math.round(+e.amt).toLocaleString(TRIP.locale||'en-IN')}`;
 return `<div class="item${EDIT===e.id?' editing':''}" onclick="editL('${e.id}')"><span class="kd">${c[0]}</span><div><div class="t">${e.what||'Spend'}${e.est?' <span class="pill" style="padding:1px 7px;font-size:10.5px">est</span>':''}</div><small>${paid}${e.cur!==(TRIP.homeCur||TRIP.cur)&&TRIP.features&&TRIP.features.fx?' · '+fmtMoney(v,HS):''}${e.edited?' · edited':''}</small></div><div class="r">${right}<button class="x" aria-label="remove" onclick="event.stopPropagation();rmL('${e.id}')">✕</button></div></div>`}
function renderL(){const el=document.getElementById('ledger');if(!el)return;const me=SPLIT==='equal'?(localStorage.getItem(MK)||''):'';
 const sorted=[...L].sort((a,b)=>(b.on||b.ts)-(a.on||a.ts));let last='',out='';for(const e of sorted){const k=dayKey(e);if(k!==last){out+=`<div class="dk">${k}</div>`;last=k}out+=rowHtml(e,me)}
 const picker=SPLIT==='equal'&&NP>1?`<div class="me">I am ${TRIP.people.map(p=>`<button class="${me===p.k?'on':''}" onclick="localStorage.setItem('${MK}','${p.k}');renderL()">${p.n}</button>`).join('')}</div>`:'';
 el.innerHTML=picker+(out||'<p class="muted">No shared spends yet.</p>');
 const paid=Object.fromEntries(TRIP.people.map(p=>[p.k,0]));let tot=0;L.forEach(e=>{const v=inr(+e.amt,e.cur);paid[e.who]=(paid[e.who]||0)+v;tot+=v});
 const bal=document.getElementById('bal'),st=document.getElementById('settle'),cs=document.getElementById('cats');
 if(SPLIT==='equal'){const share=tot/NP;bal.innerHTML=TRIP.people.map(p=>{const d=paid[p.k]-share,m=p.k===me;return `<div class="${m?'me':''}"><small>${m?'You':p.n} ${d>=0?(m?'are owed':'is owed'):(m?'owe':'owes')}</small><b class="num" style="color:${d>=0?'var(--ok)':'var(--open)'}">${fmtMoney(Math.abs(d),HS)}</b><small>paid ${fmtMoney(paid[p.k],HS)}</small></div>`}).join('')+`<div style="grid-column:1/-1;background:none;padding:4px 0"><small>Total shared ${fmtMoney(tot,HS)} · ${fmtMoney(share,HS)} each</small></div>`;
  if(st&&typeof settle==='function'){const tx=settle(Object.fromEntries(TRIP.people.map(p=>[p.k,paid[p.k]-share])),1);st.innerHTML=tx.length?`<div class="lab">Settle up · ${tx.length} transfer${tx.length>1?'s':''}, the fewest possible</div>`+tx.map(t=>`<div class="tr"><span>${NM[t.from]||t.from}</span><i>→</i><span>${NM[t.to]||t.to}</span><b class="num">${fmtMoney(t.amount,HS)}</b></div>`).join(''):(L.length?'<div class="lab">All square</div>':'')}}
 else{bal.innerHTML=`<div style="grid-column:1/-1"><small>Trip total so far</small><b class="num">${fmtMoney(tot,HS)}</b><small>${L.length} entr${L.length===1?'y':'ies'}</small></div>`;if(st)st.innerHTML=''}
 if(cs){const byCat={};L.forEach(e=>{const k=CATS[e.cat]?e.cat:'other';byCat[k]=(byCat[k]||0)+inr(+e.amt,e.cur)});cs.innerHTML=Object.entries(byCat).sort((a,b)=>b[1]-a[1]).map(([k,v])=>{const c=CATS[k]||CATS.other||['•','Other'];return `<div><small>${c[0]} ${c[1]}</small><b class="num">${fmtMoney(v,HS)}</b>${SPLIT==='equal'?`<small>${fmtMoney(v/NP,HS)} each</small>`:''}</div>`}).join('')}
 if(typeof show==='function')show();
 const EXP=TRIP.budget,real=SPLIT==='equal'?tot/NP:tot,pct=EXP?Math.min(100,Math.round(100*real/EXP)):0,dr=document.getElementById('drift');
 if(dr&&EXP){const lab=SPLIT==='equal'?'each':'whole trip';dr.innerHTML=`<div><small>Real, ${lab} so far</small><b class="num">${fmtMoney(real,HS)}</b></div><div><small>Expected, ${lab}</small><b class="num">${fmtMoney(EXP,HS)}</b></div><div class="bar"><i style="width:${pct}%"></i></div><div style="grid-column:1/-1"><small>${pct}% of the expected budget used · ${real<=EXP?fmtMoney(EXP-real,HS)+' headroom':fmtMoney(real-EXP,HS)+' over'}</small></div>`;const bs=document.getElementById('bud-sum');if(bs)bs.textContent=`${HS}${Math.round(real/1000)}k of ${HS}${Math.round(EXP/1000)}k${SPLIT==='equal'?' each':''}`}}
function editL(id){const e=L.find(x=>x.id===id);if(!e)return;EDIT=id;document.getElementById('l-what').value=e.what||'';document.getElementById('l-amt').value=e.amt;const c=document.getElementById('l-cur');if(c)c.value=e.cur;
 const es=document.getElementById('l-est');if(es)es.checked=!!e.est;if(SPLIT==='equal'&&whoBox){who=e.who;whoBox.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x.dataset.w===who))}
 if(CATS[e.cat]){cat=e.cat;drawCats()}
 document.getElementById('l-add').textContent='Save changes';document.getElementById('l-cancel').hidden=false;renderL();document.getElementById('l-what').scrollIntoView({behavior:'smooth',block:'center'})}
function cancelEdit(){EDIT=null;document.getElementById('l-what').value='';document.getElementById('l-amt').value='';const es=document.getElementById('l-est');if(es)es.checked=false;document.getElementById('l-add').textContent='Add to the trip ledger';document.getElementById('l-cancel').hidden=true;renderL()}
async function addLedger(){const amt=parseFloat(document.getElementById('l-amt').value);if(!amt){toast('Enter an amount');return}
 const c=document.getElementById('l-cur'),es=document.getElementById('l-est');const e={what:document.getElementById('l-what').value.trim(),amt,cur:c?c.value:TRIP.cur,who,cat,est:!!(es&&es.checked)};const editing=EDIT;
 try{const r=await fetch(editing?API+'/'+editing:API,{method:editing?'PUT':'POST',headers:hdr(),body:JSON.stringify(e)});if(r.status===403)return toast('Members only');if(!r.ok)return toast('Could not save ('+r.status+')');
  const saved=await r.json();L=editing?L.map(x=>x.id===editing?saved:x):[saved,...L];localStorage.setItem(LK,JSON.stringify(L));
  cancelEdit();toast(editing?'Updated for everyone':'Logged for everyone');syncLedger()}catch(x){toast('Could not reach the ledger. Try again online.')}}
async function rmL(id){if(!confirm('Remove this entry for everyone?'))return;try{const r=await fetch(API+'/'+id,{method:'DELETE',headers:hdr()});if(r.status===403)return toast('Members only');if(!r.ok)return toast('Could not remove ('+r.status+')');L=L.filter(e=>e.id!==id);if(EDIT===id)cancelEdit();renderL();toast('Removed for everyone');syncLedger()}catch(x){toast('Offline, try again later')}}
function shareLedger(){const paid=Object.fromEntries(TRIP.people.map(p=>[p.k,0]));let tot=0;L.forEach(e=>{const v=inr(+e.amt,e.cur);paid[e.who]=(paid[e.who]||0)+v;tot+=v});
 let txt=`${TRIP.name} trip spends\n`+L.map(e=>`• ${e.what||'Spend'}: ${SYM[e.cur]||TRIP.sym}${e.amt}${SPLIT==='equal'?' ('+(NM[e.who]||e.who)+')':''}`).join('\n')+`\n\nTotal ${fmtMoney(tot,HS)}`;
 if(SPLIT==='equal'){const sh=tot/NP;txt+=` · ${fmtMoney(sh,HS)} each\n`+TRIP.people.map(p=>`${p.n}: paid ${fmtMoney(paid[p.k],HS)}, ${paid[p.k]-sh>=0?'is owed':'owes'} ${fmtMoney(Math.abs(paid[p.k]-sh),HS)}`).join('\n');
  if(typeof settle==='function'){const tx=settle(Object.fromEntries(TRIP.people.map(p=>[p.k,paid[p.k]-sh])),1);if(tx.length)txt+=`\n\nSettle up:\n`+tx.map(t=>`${NM[t.from]||t.from} pays ${NM[t.to]||t.to} ${fmtMoney(t.amount,HS)}`).join('\n')}}
 if(navigator.share)navigator.share({text:txt}).catch(()=>{});else{navigator.clipboard.writeText(txt);alert('Copied')}}
if(ROLE!=='visitor'){renderL();syncLedger()}
