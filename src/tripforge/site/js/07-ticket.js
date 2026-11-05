/* ---------- ticket: next flight (boarding-pass object on the Runway page) ---------- */
function ticket(){const box=document.getElementById('ticket');if(!box)return;const n=Date.now();const flights=EVENTS.filter(x=>x.kind==='fly');if(!flights.length){box.innerHTML='';return}
 const e=flights.find(x=>new Date(x.t)>n)||flights[flights.length-1];
 const st=e.st==='ok'?'<span class="stamp ok">Booked</span>':'<span class="stamp open">To book</span>';
 const dd=new Intl.DateTimeFormat('en-GB',{weekday:'short',day:'numeric',month:'short',timeZone:e.tz||TZ}).format(new Date(e.t));
 box.innerHTML=`<div class="ticket">${st}<div class="hd"><span>Next flight</span><span>${dd}</span></div>
 <div class="route"><div><div class="code">${e.from}</div><div class="city">${e.fc}</div></div><div class="plane">✈</div><div class="r"><div class="code">${e.to}</div><div class="city">${e.tc}</div></div></div>
 <div class="tear"></div><div class="ft"><div><span>Departs</span><b class="num">${e.dep}</b></div><div><span>Arrives</span><b class="num">${e.arr}</b></div><div><span>Flight</span><b>${e.name.replace(' (to book)','')}</b></div></div>
 ${e.note?`<div style="padding:0 18px 6px;font-size:13px;color:var(--paper-ink-2)">${e.note}</div>`:''}
 <div style="padding:0 18px 10px" data-fl="${fkey(e.name)}"></div>
 <div class="act" style="display:flex;gap:8px;flex-wrap:wrap;padding:0 18px 16px"><a class="tbtn go" href="${dir(e.q||e.fc+' airport')}" target="_blank">Directions to ${e.from}</a><a class="tbtn" href="${live(e.name)}" target="_blank">Tracker</a></div></div>`}
ticket();
