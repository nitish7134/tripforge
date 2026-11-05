/* ---------- phrases (TTS) ---------- */
document.getElementById('phrases').innerHTML=PHRASES.map(([t,r,e],i)=>`<div class="ph"><div><div class="t">${t}</div><div class="e">${r} · ${e}</div></div><button aria-label="speak" onclick="say(${i})">🔊</button></div>`).join('');
function say(i){speak(PHRASES[i][0])}

