/* ---------- day deck: Page(props) per day, swipe with page-turn, strip nav ---------- */
function stamp(st){return st==='ok'?'<span class="st ok">Booked</span>':st==='open'?'<span class="st open">To book</span>':''}
function slipMove(m){
 if(m.kind==='fly')return `<div class="slip">${stamp(m.st)}<div class="lab">Flight</div><div class="tk"><div><b>${m.from}</b><span>${m.dep}</span></div><div style="color:var(--paper-ink-2)">✈</div><div class="r"><b>${m.to}</b><span>${m.arr}</span></div></div><div class="sub">${m.name}${m.sub?' · '+m.sub:''}</div><div data-fl="${fkey(m.name)}"><div class="lv"><span style="color:var(--paper-ink-2)">Live status appears here from 48 h before departure (delays, gate, belt).</span></div></div><div class="act"><a class="go" href="${dir(m.q)}" target="_blank">${I.car} Directions to ${m.from}</a><a href="${live(m.name)}" target="_blank">${I.radar} Tracker</a>${m.ref?`<button class="ref" onclick="cp('${m.ref}')">PNR ${m.ref}</button>`:''}</div></div>`;
 return `<div class="slip">${stamp(m.st)}<div class="lab">${m.kind==='rail'?'Train':m.kind==='bus'?'Bus':m.kind==='boat'?'Boat':'Travel'}</div><div class="nm">${m.name}</div>${m.sub?`<div class="sub">${m.sub}</div>`:''}<div class="act"><a class="go" href="${dir(m.q)}" target="_blank">${I.car} Directions</a>${m.ref?`<button class="ref" onclick="cp('${m.ref}')">${m.ref}</button>`:''}</div></div>`}
function slipStay(k){const s=STAYS[k];if(!s)return '';
 const pics=s.pics?`<div class="pics">${Array.from({length:s.pics},(_,i)=>`<img src="img/stays/${k}-${i+1}.jpg" alt="" loading="lazy">`).join('')}</div>`:'';
 return `<div class="slip">${stamp(s.st)}<div class="lab">Sleep tonight</div><div class="nm">${s.name}</div><div class="sub">${s.sub||''}</div>${pics}${s.addr?`<div class="sub">${s.addr}</div>`:''}${s.note?`<div class="sub" style="color:var(--open)">${s.note}</div>`:''}<div class="act"><a class="go" href="${dir(s.q)}" target="_blank">${I.pin} Directions</a>${s.local?`<button onclick="speak('${s.local.replace(/'/g,'')}')">${I.say} Say it</button>`:''}${s.book?`<a href="${s.book}" target="_blank" rel="noopener">${s.site||'Booking'}</a>`:''}${s.ref?`<button class="ref" onclick="cp('${s.ref}')">${s.ref}</button>`:''}</div></div>`}
function cp(t){navigator.clipboard&&navigator.clipboard.writeText(t).then(()=>toast('Copied '+t),()=>toast(t))}
function tixHtml(d){const rows=(d.tix||[]).flatMap(k=>TIX[k]||[]);if(!rows.length)return '';return `<h2>Tickets</h2><div class="panel">${rows.map(t=>`<div class="kv"><div><b>${t.n}</b><div class="muted">${t.p}</div></div><a href="${t.u}" target="_blank" rel="noopener">${/google\.com\/maps/.test(t.u)?'map':/wikivoyage|instagram/.test(t.u)?'info':'book'}</a></div>`).join('')}</div>`}
/* page-turn: rotate pages around the edge nearest the centre as they slide */
const RM=matchMedia('(prefers-reduced-motion: reduce)').matches;let tq=false;
function turn(){if(RM)return;const dk=document.getElementById('deck');const w=dk.clientWidth,sl=dk.scrollLeft;dk.querySelectorAll('.pg').forEach(c=>{const r=(c.offsetLeft-sl)/w;if(Math.abs(r)>1.1||Math.abs(r)<.015){c.style.transform='';c.style.opacity='';return}c.style.transformOrigin=r<0?'right center':'left center';c.style.transform=`rotateY(${(r*42).toFixed(2)}deg) translateX(${(r*-5).toFixed(2)}%)`;c.style.opacity=(1-Math.abs(r)*.45).toFixed(3)})}
document.getElementById('deck').addEventListener('scroll',()=>{if(tq)return;tq=true;requestAnimationFrame(()=>{tq=false;turn()})},{passive:true});
function sizeDeck(){const dk=document.getElementById('deck');const top=dk.getBoundingClientRect().top+window.scrollY;const nav=document.querySelector('nav').offsetHeight;document.documentElement.style.setProperty('--deckh',`calc(${Math.max(360,innerHeight-top-nav-10)}px)`)}
sizeDeck();addEventListener('resize',sizeDeck);
const MON=new Intl.DateTimeFormat('en-GB',{month:'short',timeZone:TZ}),DOW=new Intl.DateTimeFormat('en-GB',{weekday:'short',timeZone:TZ});
function timeline(){const ti=todayIdx();const last=TRIP.ndays-1;const cur=ti<0?-1:ti>last?last:ti;
 const dk=document.getElementById('deck');const keep=dk.scrollLeft;dk.querySelectorAll('.pg.day').forEach(x=>x.remove());const pre=document.getElementById('dcpre');let ps=pre.querySelector('.photo .stk');if(!ps){ps=document.createElement('span');ps.className='stk';pre.querySelector('.photo').appendChild(ps)}ps.innerHTML=THEME.stk.join('');
 dk.insertAdjacentHTML('beforeend',DAYS.map((d,i)=>{const date=dateOf(i);const isT=i===cur;const plan=planHtml(date,isT);const dt=new Date(date+'T12:00:00'+TRIP.tzOffset),mon=MON.format(dt),dow=DOW.format(dt),dn=dt.getUTCDate();
  return `<article class="pg day" id="dc${i}" data-date="${date}">${isT?'<span class="nowtag">Today</span>':''}${d.img?`<div class="photo" style="background-image:url(img/${d.img}.jpg)">${stickers()}<span class="cap">${CRED[d.img]||''}</span></div>`:'<div style="height:16px"></div>'}<div class="hd"><div class="dn">${dn}<small>${dow} · ${mon}</small></div><div><div class="where">${d.where}</div><h3>${d.h}</h3></div></div>
  ${dayWx(d,date)?`<div class="wxl">${dayWx(d,date)}</div>`:''}
  <p>${d.p}</p>
  ${(d.move||[]).map(slipMove).join('')}
  ${d.sleep?slipStay(d.sleep):`<div class="slip"><div class="lab">Sleep tonight</div><div class="nm">${d.sleepNote||'Home'}</div></div>`}
  ${tixHtml(d)}
  ${d.tpl&&document.getElementById(d.tpl)?`<h2>${d.tplh||''}</h2>${document.getElementById(d.tpl).innerHTML}`:''}
  ${plan?`<h2>${isT?'Plan for today':'Plan'}</h2>${plan}`:(d.opts?`<h2>Pick one</h2><details><summary>${d.opts.length} options</summary><ul>${d.opts.map(o=>`<li>${o}</li>`).join('')}</ul></details>`:'')}
  </article>`}).join(''));dk.scrollLeft=keep;turn();
 document.getElementById('strip').innerHTML=`<button data-i="pre" class="pre ${cur<0?'on':''}"><small>${TRIP.home}</small><b>Runway</b><i class="none"></i></button>`+DAYS.map((d,i)=>{const st=d.sleep&&STAYS[d.sleep]?STAYS[d.sleep].st:(d.move&&d.move[0].st)||'none';const dt=new Date(dateOf(i)+'T12:00:00'+TRIP.tzOffset);return `<button data-i="${i}" class="${i===cur?'on':''}"><small>${DOW.format(dt)}</small><b>${dt.getUTCDate()}</b><i class="${st}"></i></button>`}).join('');
 document.querySelectorAll('#strip button').forEach(b=>b.onclick=()=>document.getElementById('dc'+b.dataset.i).scrollIntoView({behavior:'smooth',inline:'start',block:'nearest'}));
 document.querySelectorAll('#trip .pg').forEach(c=>obs.observe(c));
 liveFlights();refreshDist()}
const obs=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){const i=e.target.id.slice(2);document.querySelectorAll('#strip button').forEach(b=>b.classList.toggle('on',b.dataset.i===i));const sb=document.querySelector(`#strip button[data-i="${i}"]`);sb&&sb.scrollIntoView({inline:'center',block:'nearest'})}}),{root:document.getElementById('deck'),threshold:.6});
timeline();
{const ti=todayIdx();if(ti>=0){const el=document.getElementById('dc'+Math.min(ti,TRIP.ndays-1));el&&requestAnimationFrame(()=>el.scrollIntoView({inline:'start',block:'nearest'}))}}
function gt(t){window.open('https://translate.google.com/?sl='+(TRIP.speakLang||'auto').slice(0,2)+'&tl=en&op=translate&text='+encodeURIComponent(t),'_blank')}
function speak(t){if(!('speechSynthesis'in window))return gt(t);const lang=TRIP.speakLang||'en';
 const run=()=>{const vs=speechSynthesis.getVoices();const v=vs.find(x=>x.lang.toLowerCase().startsWith(lang.slice(0,2).toLowerCase()));
  if(!v){toast('No voice for this language on this phone. Opening Google Translate, tap its speaker.');return gt(t)}
  const u=new SpeechSynthesisUtterance(t);u.voice=v;u.lang=v.lang;u.rate=.85;u.onerror=()=>gt(t);if(speechSynthesis.speaking)speechSynthesis.cancel();speechSynthesis.speak(u)};
 if(speechSynthesis.getVoices().length)run();else{let done=false;speechSynthesis.onvoiceschanged=()=>{if(!done){done=true;run()}};setTimeout(()=>{if(!done){done=true;run()}},500)}}
function toast(m){let t=document.getElementById('toast');if(!t){t=document.createElement('div');t.id='toast';t.style.cssText='position:fixed;left:16px;right:16px;bottom:calc(var(--tab) + env(safe-area-inset-bottom) + 10px);background:var(--paper);color:var(--paper-ink);border-radius:14px;padding:12px 14px;font-size:14px;z-index:20;box-shadow:0 8px 30px rgba(0,0,0,.4)';document.body.appendChild(t)}t.textContent=m;t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',3200)}
