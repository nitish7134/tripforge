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
 const sym=j.sym||TRIP.sym||'';const all=j.options||[];const ch=all.find(o=>o.id===j.chosen);
 const opts=ch?[ch]:all;   /* a `chosen` option is shown alone on top; the rest fold under Other options */
 const card=o=>`<div class="panel fp${o.id===(j.chosen||j.best)?' best':''}${o.over?' over':''}">
  <div class="kv"><b>${esc(o.label)}</b><span>${o.over?'<span class="pill bad">Over budget</span> ':''}${o.fails?`<span class="pill bad">${o.fails} rule${o.fails>1?'s':''} broken</span>`:'<span class="pill ok">rules met</span>'}${o.warns?` <span class="pill open">${o.warns} close call</span>`:''}</span></div>
  ${(o.legs||[]).map(l=>`<div class="fl"><small>${esc(l.who)} · ${esc(l.dir)}</small><div><b>${esc(l.flight)}</b> ${esc(l.from)} → ${esc(l.to)} · ${esc(l.depL)} → ${esc(l.arrL)}${(()=>{const v=l.verified??o.verified??j.verified;return v===true?'':' '+secEst().replace('>est<',v==='proxy'?'>proxy schedule<':'>unverified<')})()}${l.price?` · <span class="num">${esc(sym)}${secFmt(l.price)}</span>${l.pax>1?` (${esc(sym)}${secFmt(Math.round(l.price/l.pax))} each)`:''}`:''}${l.cap?(l.cap.ok?` <span class="pill ${l.cap.headroom<2000?'open':'ok'}">${esc(sym)}${secFmt(l.cap.headroom)} under cap</span>`:` <span class="pill bad">over cap by ${esc(sym)}${secFmt(-l.cap.headroom)}</span>`):''}</div></div>`).join('')}
  ${(o.results||[]).map(r=>`<div class="fr ${r.ok?'ok':r.soft?'warn':'bad'}"><span>${r.ok?'✓':r.soft?'!':'✗'}</span>${esc(r.label)}: ${esc(r.detail)}</div>`).join('')}
  <div class="kv"><span class="muted">Total, all legs${o.id===j.chosen?' · chosen':o.id===j.best?' · best pick':''}</span><b class="num">${esc(sym)}${secFmt(o.total||0)}</b></div>
  ${o.note?`<p class="muted">${esc(o.note)}</p>`:''}</div>`;
 const rest=ch?all.filter(o=>o!==ch):[];
 return (ch?`<div class="kv"><span class="pill ok">chosen plan</span></div>`:'')+opts.map(card).join('')+(rest.length?`<details class="fold"><summary>Other options (${rest.length})</summary>${rest.map(card).join('')}</details>`:'')+(j.note?`<p class="muted">${esc(j.note)}</p>`:'')}

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

function secStays(j){ /* kind "stays": places[{name|place, dates, options[]}]; options[0] is the top pick, options[1] the runner-up (or top_pick / runner_up keys); every listing links out in a new tab */
 window.SEC_STAYS_OK=true;document.querySelectorAll('.est-stays').forEach(e=>e.remove());
 const places=j.places||j.stays||(Array.isArray(j)?j:[j]);
 const card=(x,tag,best)=>{if(!x||typeof x!=='object')return'';const url=x.url||x.link||x.listing_url||x.listing;const name=x.name||x.title||'Listing';
  const ver=(x.verified??j.verified)===true;
  const nk=Object.keys(x).find(k=>/^price_night_[a-z]{3}$/.test(k)&&x[k]!=null);const nightly=nk?nk.slice(-3).toUpperCase()+' '+secFmt(x[nk]):(secMoney(x)||(x.price?esc(x.price):''));
  return`<div class="fl${best?' pick':''}"><small>${best?'★ ':''}${esc(tag)}${x.type?' · '+esc(x.type):''}${x.area?' · '+esc(x.area):''}</small><div><b>${/^https?:\/\//.test(url||'')?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(name)}</a>`:esc(name)}</b> ${ver?'':secEst().replace('>est<','>price unverified<')}${nightly?' · '+nightly+' a night':''}${x.rating?' · ★'+esc(x.rating):''}${x.reviews?' ('+esc(x.reviews)+' reviews)':''}</div>${[x.distance_note,x.couple_note,x.why,x.note].filter(Boolean).map(t=>`<div class="muted">${esc(t)}</div>`).join('')}${x.cancellation?`<div class="muted">Cancellation: ${esc(x.cancellation)}</div>`:''}${typeof x.verified==='string'?`<div class="muted">Checked: ${esc(x.verified)}</div>`:''}${x.checked_at?`<div class="muted">checked ${esc(x.checked_at)}</div>`:''}</div>`};
 return places.map(pl=>{const opts=pl.options||[];const tp=pl.top_pick||pl.top||pl.pick,rp=pl.runner_up||pl.runnerup||pl.second;   /* a string pick is the reason for options[0] / options[1]; an object is the listing itself */
  const top=tp&&typeof tp==='object'?tp:(opts[0]&&typeof tp==='string'?{...opts[0],why:tp}:opts[0]);const ru=rp&&typeof rp==='object'?rp:(opts[1]&&typeof rp==='string'?{...opts[1],why:rp}:(tp&&typeof tp==='object'?null:opts[1]));
  const rest=opts.filter(o=>o!==top&&o!==ru&&o!==opts[0]&&!(rp&&o===opts[1]));
  return`<div class="panel fp best"><div class="kv"><b>${esc(pl.name||pl.place||'')}</b><span class="muted">${esc(pl.dates||'')}${pl.nights?' · '+esc(pl.nights)+' night'+(pl.nights>1?'s':''):''}</span></div>${pl.base_area?`<div class="muted">Base: ${esc(pl.base_area)}</div>`:''}${card(top,'Top pick',true)}${card(ru,'Runner-up')}${rest.length?`<details class="fold"><summary>More options (${rest.length})</summary>${rest.map(o=>card(o,'Option')).join('')}</details>`:''}${pl.area_comparison?`<p class="muted">${esc(pl.area_comparison)}</p>`:''}${pl.note?`<p class="muted">${esc(pl.note)}</p>`:''}</div>`}).join('')+((j.assumptions||[]).length?`<details class="fold"><summary>Assumptions</summary>${(j.assumptions).map(x=>`<div class="fr"><span>•</span>${esc(x)}</div>`).join('')}</details>`:'')+(j.note?`<p class="muted">${esc(j.note)}</p>`:'')}

function secBook(j){ /* kind "book": legs|rows|items[{leg|route|who, flight, price|price_<cur>, available|availability|status, url|book_url|link, checked_at}], total|total_<cur> */
 const rows=j.legs||j.rows||j.items||j.flights||(Array.isArray(j)?j:[]);const sym=j.sym||'';
 const avail=v=>{if(v===true||/^(ok|yes|open|available|listed|seats? available|bookable)/i.test(String(v)))return['ok',v===true?'available':String(v)];
  if(/^changed/i.test(String(v)))return['open','price changed'];
  if(v===false||/(sold ?out|unavailable|not available|full|cancel)/i.test(String(v)))return['bad',v===false?'not available':String(v)];
  return['open',v==null||v===''?'not checked':String(v)]};
 const price=x=>{const k=Object.keys(x).find(k=>/^price(_[a-z]{3})?$/.test(k)&&x[k]!=null&&typeof x[k]!=='object');if(!k)return'';const c=k.length>5?k.slice(-3).toUpperCase()+' ':sym;return c+secFmt(x[k])};
 const out=rows.map(x=>{const [cls,txt]=avail(x.available??x.availability??x.status);const links=x.booking_links&&typeof x.booking_links==='object'?Object.entries(x.booking_links).filter(([k,u])=>/^https?:\/\//.test(u||'')):[];const url=x.url||x.book_url||x.booking_url||x.link;
  const wk=Object.keys(x).find(k=>/^(old|previous)_price(_[a-z]{3})?$/.test(k));const was=wk?x[wk]:x.was;const same=was!=null&&Number(was)===Number(x[Object.keys(x).find(k=>/^price(_[a-z]{3})?$/.test(k))]);
  return`<div class="fl"><small>${esc(x.who||x.leg||'')}${x.route?' · '+esc(x.route):''}${x.date?' · '+esc(x.date):''}</small><div><b>${esc(x.flight||x.flight_no||x.name||'')}</b>${x.dep?` ${esc(x.dep)}${x.arr?' → '+esc(x.arr):''}`:''} <span class="pill ${cls}">${esc(txt)}</span>${price(x)?` · <span class="num">${price(x)}</span>`:''}${was!=null&&!same?` <span class="muted">(was ${secFmt(was)})</span>`:''}${/^https?:\/\//.test(url||'')?` · <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">book</a>`:''}${links.map(([k,u])=>` · <a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(k.replace(/_/g,' '))}</a>`).join('')}</div>${x.checked_at?`<div class="muted">checked ${esc(x.checked_at)}</div>`:''}${x.note?`<div class="muted">${esc(x.note)}</div>`:''}</div>`}).join('');
 const tk=Object.keys(j).find(k=>/^(new_)?total(_[a-z]{3})?$/.test(k)&&j[k]!=null&&typeof j[k]!=='object');
 const total=tk?(tk.match(/_([a-z]{3})$/)?tk.slice(-3).toUpperCase()+' ':sym)+secFmt(j[tk]):'';
 return`<div class="panel fp best">${out||'<p class="muted">No legs in the file yet.</p>'}${total?`<div class="kv"><b>New total, all legs</b><b class="num">${total}</b></div>`:''}${j.checked_at?`<p class="muted">Checked ${esc(j.checked_at)}${j.source?' · '+esc(j.source):''}</p>`:''}<p class="muted">Not booked. Prices and seats change; confirm on the booking page before paying.</p>${j.note?`<p class="muted">${esc(j.note)}</p>`:''}</div>`}

function secBrief(j){ /* kind "brief": assumptions[{t,d}], changes[{t,d}] ("what changes if"), budget{rows[[label,value,note]], total, note} */
 const list=(a)=>(a||[]).map(x=>typeof x==='string'?`<div class="fr"><span>•</span>${esc(x)}</div>`:`<div class="fl"><div><b>${esc(x.t)}</b></div>${x.d?`<div class="muted">${esc(x.d)}</div>`:''}</div>`).join('');
 let o='';const S=j.summary;
 if(S)o+=`<div class="panel fp best"><div class="kv"><b>${esc(S.title||'At a glance')}</b>${S.total?`<b class="num">${esc(S.total)}</b>`:''}</div>${[['Who',S.who],['Dates',S.dates],['Route',S.route]].filter(r=>r[1]).map(r=>`<div class="kv"><span class="muted">${r[0]}</span><span>${esc(r[1])}</span></div>`).join('')}${(S.book_first||[]).length?`<div class="fl"><small>Book first</small>${S.book_first.map((b,i)=>`<div>${i+1}. ${/^https?:\/\//.test(b.u||'')?`<a href="${esc(b.u)}" target="_blank" rel="noopener noreferrer">${esc(b.t)}</a>`:esc(b.t)}${b.d?` <span class="muted">${esc(b.d)}</span>`:''}</div>`).join('')}</div>`:''}${(S.checks||[]).map(c=>`<div class="fr ${c.ok==='warn'?'warn':c.ok?'ok':'bad'}"><span>${c.ok==='warn'?'!':c.ok?'✓':'✗'}</span>${esc(c.t)}</div>`).join('')}</div>`;
 if((j.assumptions||[]).length)o+=`<div class="panel fp"><div class="kv"><b>${esc(j.assumptionsTitle||'Assumptions')}</b>${j.badge?`<span class="pill open">${esc(j.badge)}</span>`:''}</div>${list(j.assumptions)}</div>`;
 if((j.changes||[]).length)o+=`<details class="fold"><summary>${esc(j.changesTitle||'What changes if…')}</summary><div class="panel">${list(j.changes)}</div></details>`;
 const b=j.budget;if(b&&(b.rows||[]).length)o+=`<details class="fold" open><summary>${esc(b.title||'Rough budget')}</summary><div class="panel">${b.rows.map(r=>`<div class="kv"><span>${esc(r[0])}${r[2]?`<div class="muted">${esc(r[2])}</div>`:''}</span><b class="num">${esc(r[1])}</b></div>`).join('')}${b.total?`<div class="kv"><b>Total</b><b class="num">${esc(b.total)}</b></div>`:''}${b.note?`<p class="muted">${esc(b.note)}</p>`:''}</div></details>`;
 return o}
/* ---------- kind "dayGuide": day selector, hour-by-hour timeline, meals, nightlife, activities, backup, budget, book-ahead (prepared by dayguide.py) ---------- */
const dgA=(u,t,c)=>/^https:\/\//.test(u||'')?`<a${c?` class="${c}"`:''} href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(t)}</a>`:'';
const DG_ICON={fly:'✈️',move:'🚕',eat:'🍜',drink:'🍸',beach:'🏖️',see:'📍',rest:'🛏️',book:'🎟️',night:'🌙'};
function dgRow(x,left){
 const unv=x.verified?'':' '+secEst().replace('>est<','>unverified<');const est='est ';
 const h=x.how;const how=h?(typeof h==='string'?h:[h.text,h.mins?h.mins+' min':'',h.cost_p?est+h.cost_p.label:''].filter(Boolean).join(' · ')):'';
 const m=[['Hours',x.hours],['Cost',x.cost_p&&est+x.cost_p.label],['Entry',x.entry_p?est+x.entry_p.label:x.entry],['Drinks',x.drinks_p?est+x.drinks_p.label:x.drinks],['Dress',x.dress],['Getting there',how],['Safety',x.safety],['Tip',x.tip]]
  .filter(r=>r[1]).map(r=>`<div class="dg-m"><span>${r[0]}</span>${esc(r[1])}</div>`).join('');
 const ord=(x.order||[]).length?`<div class="dg-m"><span>Order</span>${x.order.map(o=>typeof o==='string'?esc(o):esc(o.dish)+(o.cost_p?' <i>'+esc(est+o.cost_p.label)+'</i>':'')).join(' · ')}</div>`:'';
 const links=[x.name?dgA(x.maps,'Google Maps','dg-map'):'',dgA(x.url,x.url_label||'Book / info'),dgA(x.src,'source')].filter(Boolean).join(' ');
 const title=x.title||x.name;const sub=x.title&&x.name?`<div class="dg-pl">${esc(x.name)}${x.area?' · '+esc(x.area):''}</div>`:(x.area&&!x.title?`<div class="dg-pl">${esc(x.area)}</div>`:'');
 return `<div class="dg-row"><div class="dg-t">${left}</div><div class="dg-b"><b>${x.kind&&DG_ICON[x.kind]?DG_ICON[x.kind]+' ':''}${esc(title)}</b>${unv}${sub}${x.why?`<div>${esc(x.why)}</div>`:''}${m}${ord}${links?`<div class="dg-l">${links}</div>`:''}</div></div>`}
function dgTime(x){return `<span>${esc(x.time)}</span>${x.end?`<small>${esc(x.end)}</small>`:''}`}
function secDayGuide(j){
 const fx=j.fx||{};const days=j.days||[];if(!days.length)return'';
 let today='';try{today=new Date().toLocaleDateString('en-CA',{timeZone:TRIP.tz||undefined})}catch(e){}
 window.SEC_DAYSEL=window.SEC_DAYSEL||{};const key=j.id||'dg';
 const sel=days.find(d=>d.id===window.SEC_DAYSEL[key])||days.find(d=>d.date===today)||days[0];
 const fold=(h,b,open)=>b?`<details class="fold"${open?' open':''}><summary>${esc(h)}</summary><div class="panel">${b}</div></details>`:'';
 const list=(a,f)=>(a||[]).map(f).join('');
 const panel=d=>{const L=(a)=>(a||[]).map(x=>`<div class="fr"><span>•</span>${esc(x)}</div>`).join('');
  const bk=d.backup;const bud=d.budget;
  return `<div class="dg-day" data-d="${esc(d.id)}"${d===sel?'':' hidden'}>
   <h3>${esc(d.title)}</h3>${d.summary?`<p class="muted">${esc(d.summary)}</p>`:''}
   ${(d.warn||[]).map(w=>`<div class="fr bad"><span>!</span>${esc(w)}</div>`).join('')}
   ${fold('Hour by hour',list(d.timeline,x=>dgRow(x,dgTime(x))),true)}
   ${fold('Where to eat',list(d.eat,x=>dgRow(x,`<span>${esc(x.meal||'')}</span>`)))}
   ${fold('Drinks and nightlife',list(d.nightlife,x=>dgRow(x,`<span>${esc(x.time||'')}</span>`)))}
   ${fold('Beaches and things to do',list(d.do,x=>dgRow(x,`<span>${DG_ICON[x.kind]||'📍'}</span>`)))}
   ${bk?fold(bk.title||'Rain or low-energy backup',(bk.text?`<p>${esc(bk.text)}</p>`:'')+list(bk.items,x=>dgRow(x,`<span>${DG_ICON[x.kind]||'☂️'}</span>`))):''}
   ${bud?fold('Budget for the day (both, est)',list(bud.rows,r=>`<div class="kv"><span>${esc(r.item)}${r.note?`<div class="muted">${esc(r.note)}</div>`:''}</span><b class="num">${esc(r.p.label)}</b></div>`)+`<div class="kv"><b>Day total</b><b class="num">${esc(bud.total.label)}</b></div>${bud.note?`<p class="muted">${esc(bud.note)}</p>`:''}`,true):''}
   ${fold('Book ahead',list(d.book,b=>`<div class="fl"><div><b>${dgA(b.u,b.t)||esc(b.t)}</b>${b.d?`<div class="muted">${esc(b.d)}</div>`:''}</div></div>`),true)}
   ${fold('Notes',L(d.notes),!!(d.notes_open))}</div>`};
 const tabs=days.map(d=>`<button type="button" class="dg-tab" data-dg-day="${esc(d.id)}" aria-pressed="${d===sel}">${esc(d.tab||d.date)}${d.date===today?' <small>today</small>':''}</button>`).join('');
 const tt=j.trip_total&&j.trip_total.hi?`<p class="muted">Days add up to about ${esc(fx.to||'')} ${secFmt(j.trip_total.lo)}-${secFmt(j.trip_total.hi)} on the ground (est, excludes flights and stays).</p>`:'';
 return `<div class="dg" data-k="${esc(key)}"><div class="panel fp"><div class="kv"><span>${secEst()} <b>Prices are estimates.</b></span></div><p class="muted">1 ${esc(fx.from)} = ${esc(fx.to)} ${esc(fx.rate)}, ${esc(fx.date)}${fx.source?' · '+dgA(fx.source,'rate source'):''}. Anything with an unverified badge was not confirmed for 21-24 Nov: check hours and prices before relying on them.</p>${j.intro?`<p class="muted">${esc(j.intro)}</p>`:''}${tt}</div>
  <div class="dg-tabs" role="group" aria-label="Pick a day">${tabs}</div>${days.map(panel).join('')}</div>`}
if(!window.SEC_DG_BOUND){window.SEC_DG_BOUND=1;document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('[data-dg-day]');if(!b)return;const w=b.closest('.dg');if(!w)return;
 const id=b.dataset.dgDay;window.SEC_DAYSEL=window.SEC_DAYSEL||{};window.SEC_DAYSEL[w.dataset.k]=id;
 w.querySelectorAll('.dg-day').forEach(p=>{p.hidden=p.dataset.d!==id});w.querySelectorAll('.dg-tab').forEach(t=>t.setAttribute('aria-pressed',String(t.dataset.dgDay===id)))})}
const SEC_RENDER={brief:secBrief,book:secBook,flightPlan:secFlights,itinerary:secItinerary,stays:secStays,dayGuide:secDayGuide};
async function secLoad(s,box){
 const body=box.querySelector('.sb'),ac=new AbortController(),to=setTimeout(()=>ac.abort(),SEC_TTL);
 try{const r=await fetch(`data/${s.id}.json`,{cache:'no-store',signal:ac.signal});
  if(r.status===404){if(!box.dataset.ok)body.innerHTML=`<p class="muted">${esc(s.pending||'Coming soon. This part is still being researched.')}</p>`;return}
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
