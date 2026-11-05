/* ---------- phrases (tap to hear), only rendered when DATA.phrases is non-empty ---------- */
{const box=document.getElementById('phrases');if(box&&PHRASES.length){box.innerHTML=PHRASES.map(([t,r,e],i)=>`<div class="ph"><div><div class="t">${t}</div><div class="e">${r} · ${e}</div></div><button aria-label="speak" onclick="say(${i})">🔊</button></div>`).join('')}}
function say(i){speak(PHRASES[i][0])}
