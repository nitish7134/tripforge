/* ---------- role: visitors see no money; anyone can re-enter a PIN (upgrade) or lock the page ---------- */
function applyRole(){const q=new URLSearchParams(location.search).get('theme');if(ROLE==='visitor')applyTheme(VISITOR_THEME);else applyTheme(q&&THEMES[q]?q:(localStorage.getItem('theme')||TRIP.defaultTheme),!!q);themePicker();
 const lk=document.getElementById('lockrow');if(lk)lk.querySelector('small').textContent=ROLE==='visitor'?'Signed in as visitor':'Signed in as member';
 if(ROLE!=='visitor')return;const m=document.getElementById('money');
 if(TRIP.cover)document.documentElement.style.setProperty('--frozen-bg',`url(img/${TRIP.cover}.jpg)`);
 m.innerHTML=`<div class="frozen"><div><h3>Members only</h3><p>The shared ledger and budget are for the people travelling.</p>
  <details class="upg"><summary>I have the member PIN</summary><div class="dots" id="up-dots"><i></i><i></i><i></i><i></i></div><p class="note" id="up-note">Enter it once; this phone stays a member.</p><div class="keys" id="up-keys"></div></details></div></div>`;
 pinPad('up-keys','up-dots','up-note',async pin=>{const r=await unlockWith(pin);if(r.ok){localStorage.setItem('role','member');location.reload();return 'Welcome back'}return r.msg})}
async function unlockWith(pin){try{const r=await fetch('api/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin}),credentials:'same-origin'});
 if(r.status===204)return {ok:true};const j=await r.json().catch(()=>({}));
 return {ok:false,msg:r.status===429?`Too many tries. Wait ${Math.ceil((j.retry||600)/60)} min.`:j.left!=null?`Wrong PIN · ${j.left} tries left`:'Wrong PIN'}}catch(e){return {ok:false,msg:'Offline. Try again.'}}}
/* shared 0-9 keypad: pinPad(keysId, dotsId, noteId, onFull) -> onFull(pin) returns a message (or 'Welcome…' on success) */
function pinPad(kid,did,nid,onFull){const keys=document.getElementById(kid),dots=document.getElementById(did),note=document.getElementById(nid);let buf='',busy=false;
 keys.innerHTML=['1','2','3','4','5','6','7','8','9','','0','del'].map(k=>k===''?'<span></span>':`<button type="button" class="${k==='del'?'sm':''}" data-k="${k}">${k==='del'?'⌫':k}</button>`).join('');
 const draw=()=>dots.querySelectorAll('i').forEach((d,i)=>d.classList.toggle('on',i<buf.length));
 const fail=m=>{dots.classList.add('bad');note.textContent=m;if(navigator.vibrate)navigator.vibrate(80);setTimeout(()=>{buf='';draw();dots.classList.remove('bad')},600)};
 keys.onclick=async e=>{const b=e.target.closest('button');if(!b||busy)return;const k=b.dataset.k;
  if(k==='del'){buf=buf.slice(0,-1);draw();return}if(buf.length>=4)return;buf+=k;draw();
  if(buf.length===4){busy=true;note.textContent='Checking…';const m=await onFull(buf);busy=false;if(/^Welcome/.test(m))note.textContent=m;else fail(m)}}}
async function lockPage(){try{await fetch('api/logout',{method:'POST',credentials:'same-origin'})}catch(e){}localStorage.removeItem('role');location.replace('./')}
async function whoami(){try{const r=await fetch('api/me',{cache:'no-store'});if(!r.ok)return;const j=await r.json();if(j.role&&j.role!==ROLE){ROLE=j.role;localStorage.setItem('role',ROLE);location.reload()}ROLE=j.role||ROLE;localStorage.setItem('role',ROLE);applyRole()}catch(e){applyRole()}}
applyRole();whoami();
