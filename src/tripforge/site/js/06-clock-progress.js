/* ---------- clocks + progress. Header shows home time and destination time (one clock when they match). ---------- */
const fmtT=new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:TZ});
const fmtH=new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:TRIP.homeTz||TZ});
function clock(){const n=new Date();const c=document.getElementById('clk');if(c)c.textContent=fmtT.format(n);const h=document.getElementById('clk-h');if(h)h.textContent=fmtH.format(n);const d=document.getElementById('clk-d');if(d)d.textContent=new Intl.DateTimeFormat('en-GB',{weekday:'short',day:'numeric',month:'short',timeZone:TZ}).format(n)}
clock();setInterval(clock,15000);
const T0=new Date(TRIP.t0),T1=new Date(TRIP.t1);
function progress(){const n=Date.now(),h=document.getElementById('prog-h'),s=document.getElementById('prog-s'),i=document.getElementById('prog-i');if(!h)return;
 if(n<T0){const d=Math.floor((T0-n)/864e5),hh=Math.floor((T0-n)%864e5/36e5);h.textContent=`${d} days ${hh} h to take-off`;const pd=document.getElementById('pre-dn');if(pd){pd.firstChild.textContent=d;document.getElementById('pre-sm').textContent=d===1?'day out':'days out'}i.style.width=Math.max(2,100-100*(T0-n)/(T0-new Date(TRIP.built)))+'%'}
 else if(n<T1){const day=Math.floor((n-new Date(TRIP.start+'T00:00:00'+TRIP.tzOffset))/864e5)+1;h.textContent=`Day ${day} of ${TRIP.ndays}`;if(s&&TRIP.greeting)s.textContent=TRIP.greeting;i.style.width=(100*(n-T0)/(T1-T0))+'%'}
 else{h.textContent='Trip done. Photos time.';i.style.width='100%'}}
progress();setInterval(progress,6e4);
