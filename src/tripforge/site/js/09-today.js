/* ---------- position + distances (asks for location on open, keeps watching) ---------- */
let POS=JSON.parse(localStorage.getItem('pos')||'null');
const SPEED=TRIP.roadKmh||25; // assumed road speed for ETAs
function km(a,b,c,d){const r=Math.PI/180,x=(c-a)*r,y=(d-b)*r,h=Math.sin(x/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin(y/2)**2;return 6371*2*Math.asin(Math.sqrt(h))}
function eta(k){if(k<1.6)return `${Math.max(1,Math.round(k*12))} min walk`;if(k>300)return 'you are not there yet';if(k>60)return `${(k/60).toFixed(1)} h by road`;return `~${Math.round(k/SPEED*60)} min by road`}
function todayIdx(){const i=Math.floor((Date.now()-new Date(TRIP.start+'T00:00:00'+TRIP.tzOffset))/864e5);return i<0?-1:i>TRIP.ndays-1?TRIP.ndays:i}
function locNote(){if(!POS)return 'Allow location to see how far each place is from you.';const age=Math.round((Date.now()-POS.ts)/6e4);return `Distances from your location, ±${Math.round(POS.acc)} m, ${age<1?'just now':age+' min ago'}. Times assume ${SPEED} km/h on the road.`}
function refreshDist(){document.querySelectorAll('.pl[data-la]').forEach(r=>{const el=r.querySelector('.dist');if(!POS||!el)return;const d=km(POS.la,POS.lo,+r.dataset.la,+r.dataset.lo);el.innerHTML=`<span class="far">${d<10?d.toFixed(1):Math.round(d)} km</span> · ${eta(d)}`});const n=document.getElementById('locnote');if(n)n.textContent=locNote()}
function onPos(p){POS={la:p.coords.latitude,lo:p.coords.longitude,acc:p.coords.accuracy,ts:Date.now()};localStorage.setItem('pos',JSON.stringify(POS));refreshDist()}
function onPosErr(e){const n=document.getElementById('locnote');if(n)n.textContent=e.code===1?'Location is blocked for this site. Allow it in the browser settings to see distances.':'Waiting for a GPS fix…'}
function startLocation(){if(!navigator.geolocation)return;navigator.geolocation.getCurrentPosition(onPos,onPosErr,{enableHighAccuracy:false,timeout:15000,maximumAge:120000});
 navigator.geolocation.watchPosition(onPos,onPosErr,{enableHighAccuracy:true,maximumAge:30000,timeout:20000})}
