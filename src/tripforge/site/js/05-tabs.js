/* ---------- tabs ---------- */
function go(id){document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id===id));document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.s===id));history.replaceState(null,'','#'+id);scrollTo({top:0});if(id==='trip')requestAnimationFrame(sizeDeck)}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>go(b.dataset.s));
if(location.hash&&document.getElementById(location.hash.slice(1)))go(location.hash.slice(1));

