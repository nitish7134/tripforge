/* ---------- checklists ---------- */
function chk(id,items){const st=JSON.parse(localStorage.getItem('chk-'+id)||'{}');document.getElementById(id).innerHTML=items.map((t,i)=>`<li><label><input type="checkbox" data-i="${i}" ${st[i]?'checked':''}><span>${t}</span></label></li>`).join('');
 const cnt=()=>{const c=document.getElementById('cnt-'+id);if(c)c.textContent=`${Object.values(st).filter(Boolean).length} / ${items.length}`};cnt();
 document.querySelectorAll('#'+id+' input').forEach(c=>c.onchange=()=>{st[c.dataset.i]=c.checked;localStorage.setItem('chk-'+id,JSON.stringify(st));cnt()})}
function resetChk(id){localStorage.removeItem('chk-'+id);chk(id,id==='todo'?TODO:PACK)}
chk('todo',TODO);chk('pack',PACK);

