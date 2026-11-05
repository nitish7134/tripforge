/* ---------- clock + progress ---------- */
const fmtT=new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:TZ});
const fmtI=new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:TRIP.homeTz});
function clock(){const n=new Date();document.getElementById('clk').textContent=fmtT.format(n);document.getElementById('clk-i').textContent=fmtI.format(n)}clock();setInterval(clock,15000);
const T0=new Date(TRIP.depart),T1=new Date(TRIP.back),TP=new Date(TRIP.planned);
/* local midnight of DAYS[0]: the offset is read from the first EVENTS entry that happens there */
function day0(){if(TRIP.day0.includes('T'))return new Date(TRIP.day0);const e=EVENTS.find(x=>x.kind!=='fly')||EVENTS[0];const off=(e.t.match(/[+-]\d\d:\d\d$/)||['Z'])[0];return new Date(TRIP.day0+'T00:00:00'+off)}
function progress(){const n=Date.now(),h=document.getElementById('prog-h'),s=document.getElementById('prog-s'),i=document.getElementById('prog-i');
 if(n<T0){const d=Math.floor((T0-n)/864e5),hh=Math.floor((T0-n)%864e5/36e5);h.textContent=d>1?TRIP.tagline:`Take-off in ${hh} h`;const pd=document.getElementById('pre-dn');if(pd){pd.firstChild.textContent=d;document.getElementById('pre-sm').textContent=d===1?'day out':'days out'}i.style.width=Math.max(2,100-100*(T0-n)/(T0-TP))+'%'}
 else if(n<T1){const day=Math.floor((n-day0())/864e5)+1;h.textContent=`Day ${day} of ${DAYS.length}`;s.textContent=TRIP.hello;i.style.width=(100*(n-T0)/(T1-T0))+'%'}
 else{h.textContent='Trip done. Photos time.';i.style.width='100%'}}
progress();setInterval(progress,6e4);
