/* ---------- shell: fills the static parts of index.html from TRIP / STAYS / KIT. No trip values in this file. ---------- */
const TZ=TRIP.tz;
const NAMES=TRIP.people,WHO=Object.keys(NAMES),NP=WHO.length;
const isMember=()=>ROLE!=='visitor';
(function shell(){
 const $=id=>document.getElementById(id),set=(id,h)=>{const el=$(id);if(el)el.innerHTML=h};
 $('ttl').textContent=TRIP.title;$('clk-l').textContent=TRIP.tzLabel;$('clk-il').textContent=TRIP.homeLabel;
 // first page
 const ph=$('pre-photo');if(TRIP.cover){ph.style.backgroundImage=`url(img/${TRIP.cover}.jpg)`;$('pre-cap').textContent=CRED[TRIP.cover]||''}else ph.remove();
 $('pre-where').textContent=`${TRIP.home.city} · ${TRIP.home.code}`;
 const legs=EVENTS.filter(e=>e.kind==='fly'||e.kind==='stay'),booked=legs.filter(e=>e.st==='ok').length;
 $('pill-booked').textContent=booked===legs.length?`All ${legs.length} booked`:`${booked} of ${legs.length} booked`;
 if(booked!==legs.length)$('pill-booked').classList.remove('ok');
 $('pill-nights').textContent=`${DAYS.length-1} nights`;
 $('prog-s').textContent=new Intl.DateTimeFormat('en-GB',{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:TRIP.homeTz}).format(new Date(TRIP.depart));
 set('wx',TRIP.cities.map(c=>`<div><small>${esc(c.n)}</small><span class="t">…</span></div>`).join(''));
 // money
 set('quick',TRIP.cur.quick.map(v=>`<button onclick="setA(${v})">${v.toLocaleString(TRIP.cur.locale)}</button>`).join(''));
 $('k-split').textContent='÷'+NP;
 set('l-cur',[TRIP.cur.here,TRIP.cur.home].map(c=>`<option>${c}</option>`).join(''));
 set('l-who',WHO.map((w,i)=>`<button data-w="${w}" class="${i?'':'on'}">${esc(NAMES[w])}</button>`).join(''));
 $('split-h').textContent=`Shared spends · split ${NP} ways`;
 const F=KIT.fares;if(F&&F.rows.length)set('fares',`<h2>Fares to expect</h2><div class="panel"><table><tr><th>Leg</th><th class="r">${esc(F.unit)}</th></tr>${F.rows.map(([l,v])=>`<tr><td>${esc(l)}</td><td class="r num">${esc(v)}</td></tr>`).join('')}</table>${F.note?`<p class="muted">${esc(F.note)}</p>`:''}</div>`);
 const sym=TRIP.cur.symHome,fmt=v=>sym+Math.round(v).toLocaleString(TRIP.cur.locale);
 set('bud-lines',TRIP.budget.lines.map(([l,v])=>`<div class="kv"><span>${esc(l)}</span><b class="num">${fmt(v)}</b></div>`).join('')+`<div class="kv"><b>Expected, each</b><b class="num">${fmt(TRIP.budget.each)}</b></div>${TRIP.budget.note?`<p class="muted">${esc(TRIP.budget.note)}</p>`:''}`);
 // kit
 const seen=new Set(),acts=(q,book)=>`<div class="acts"><a class="act" href="${dir(q)}" target="_blank">Directions</a><button class="act" onclick="speak(this.closest('.taxi').querySelector('.th').textContent)">Speak</button><button class="act" onclick="cp(this.closest('.taxi').querySelector('.th').textContent)">Copy</button>${book?`<a class="act" href="${esc(book)}" target="_blank" rel="noopener">Listing</a>`:''}</div>`;
 let tx=Object.values(STAYS).filter(s=>!seen.has(s)&&seen.add(s)).map(s=>`<div class="taxi"><div class="cap">${esc(s.cap||s.name)}</div><div class="th">${esc(s.th)}</div><div class="en">${esc(s.addr||s.name)}</div>${acts(s.q,s.book)}</div>`).join('');
 const A=KIT.airportCard;if(A&&A.say.length)tx+=`<div class="taxi"><div class="cap">${esc(A.cap)}</div><div class="th" style="font-size:22px">${A.say.map(x=>esc(x[0])).join('<br>')}</div><div class="en">${A.say.map(x=>esc(x[1])).join(' · ')}</div><div class="acts">${A.say.map((x,i)=>`<button class="act" onclick="speak(KIT.airportCard.say[${i}][0])">${esc(x[1])}</button>`).join('')}</div></div>`;
 set('taxis',tx);
 $('ph-h').textContent=`Say it in ${TRIP.voice.name}, tap to hear`;
 set('sos',KIT.sos.map(([n,s,t])=>`<div class="call"><div><b>${esc(n)}</b>${s?`<div class="muted">${esc(s)}</div>`:''}</div><a href="tel:${esc(t.replace(/[^+\d]/g,''))}">${esc(t)}</a></div>`).join('')+
  (KIT.hospitals.length?`<div class="call hosp"><div><b>Hospitals</b><div class="muted">24 h ER</div></div><span></span></div><div class="chips hospchips">${KIT.hospitals.map(([l,q])=>`<a href="https://maps.google.com/?q=${encodeURIComponent(q)}" target="_blank">${esc(l)}</a>`).join('')}</div>`:''));
 if(isMember()&&KIT.bookings.length)set('bookings',`<h2>Bookings &amp; refs · tap to copy</h2><div class="panel">${KIT.bookings.map(b=>`<div class="kv"><div><b>${b.u?`<a href="${esc(b.u)}" target="_blank" rel="noopener">${esc(b.t)}</a>`:esc(b.t)}</b><div class="muted">${esc(b.sub)}</div></div>${b.ref?`<button class="ref" onclick="cp('${esc(b.ref)}')">${esc(b.ref)}</button>`:'<span></span>'}</div>`).join('')}</div>`);
 if(KIT.tips.length)set('tips',`<h2>Street smarts</h2><div class="panel"><ul style="margin:0 0 0 18px;padding:0">${KIT.tips.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></div>`);
 set('foot',`${esc(KIT.foot||'')} Built with <a href="https://github.com/nitish7134/tripforge" target="_blank">tripforge</a>.`);
})();
