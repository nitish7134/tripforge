/* ---------- role: member vs visitor (only when TRIP.features.visitorRole). Visitors are pinned to the PG theme and see no Money. ---------- */
function applyRole(){const q=new URLSearchParams(location.search).get('theme');
 if(ROLE==='visitor')applyTheme(TRIP.visitorTheme||'pg13');else applyTheme(q&&THEMES[q]?q:(localStorage.getItem('theme')||TRIP.defaultTheme),!!q);
 themePicker();if(ROLE!=='visitor')return;const m=document.getElementById('money');if(m)m.innerHTML=`<div class="frozen" style="background-image:url(img/${TRIP.frozenImg||'lockbg'}.jpg)"><div><h3>Members only</h3><p>The shared ledger and budget are for the people travelling. Ask for the member PIN if you should be in here.</p></div></div>`}
async function whoami(){try{const r=await fetch('api/me',{cache:'no-store'});if(r.status===403){location.reload();return}if(!r.ok)return;const j=await r.json();if(j.role&&j.role!==ROLE){ROLE=j.role;localStorage.setItem('role',ROLE);location.reload()}ROLE=j.role||ROLE;localStorage.setItem('role',ROLE);applyRole()}catch(e){applyRole()}}
applyRole();whoami();
