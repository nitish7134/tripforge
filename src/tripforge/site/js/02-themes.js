/* ---------- themes: palette + decoration + PG filter. Four-field contract: name, deco, stk, pg. ---------- */
const tile=e=>e.length?`url("data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><text x='18' y='64' font-size='42' transform='rotate(-16 18 64)'>${e[0]}</text><text x='140' y='96' font-size='34' transform='rotate(18 140 96)'>${e[1]||e[0]}</text><text x='56' y='186' font-size='38' transform='rotate(9 56 186)'>${e[2]||e[0]}</text><text x='170' y='214' font-size='30' transform='rotate(-24 170 214)'>${e[3]||e[1]||e[0]}</text></svg>`)}")`:'none';
const THEMES=Object.assign({
 party:{name:'Party',deco:['🍃','🍺','🚬','🥃'],stk:['🍃','🍺','🔥'],pg:false},
 'party-drinks':{name:'Drinks',deco:['🍺','🥃','🍹','🍾'],stk:['🍺','🥃','🎉'],pg:false},
 'party-smoke':{name:'Smoke',deco:['🍃','🚬','💨','🔥'],stk:['🍃','💨'],pg:false},
 beach:{name:'Beach',deco:['🌴','🌊','🥥','🍹'],stk:['🌴','🌊'],pg:false},
 birthday:{name:'Birthday',deco:['🎂','🎈','🥤','🎁'],stk:['🎂','🎈'],pg:true},
 pg13:{name:'Family',deco:['🌊','🐚','🌞','🍦'],stk:['🐚','🌞'],pg:true},
 mountain:{name:'Mountain',deco:['🏔','🌲','🔥','☕'],stk:['🏔','🌲'],pg:true},
 city:{name:'City',deco:['🏙','🚇','🍜','🎧'],stk:['🏙','🎧'],pg:false},
 plain:{name:'Plain',deco:[],stk:[],pg:false}},DATA.themes||{});
let THEME=THEMES[TRIP.defaultTheme]||THEMES.plain;
function applyTheme(n,save){if(!THEMES[n])n=TRIP.defaultTheme;THEME=THEMES[n];document.documentElement.dataset.theme=n;document.documentElement.classList.toggle('pgmode',!!THEME.pg);document.documentElement.style.setProperty('--deco',tile(THEME.deco));
 if(save)localStorage.setItem('theme',n);document.querySelectorAll('#themes button').forEach(b=>b.classList.toggle('on',b.dataset.t===n));if(typeof timeline==='function')timeline()}
function stickers(){return THEME.stk.length?`<span class="stk">${THEME.stk.join('')}</span>`:''}
function themePicker(){const box=document.getElementById('themebox');if(!box)return;if(ROLE==='visitor'){box.hidden=true;return}box.hidden=false;
 document.getElementById('themes').innerHTML=Object.entries(THEMES).map(([k,t])=>`<button data-t="${k}" class="${THEME===t?'on':''}">${t.stk[0]||'◻'} ${t.name}</button>`).join('');
 document.querySelectorAll('#themes button').forEach(b=>b.onclick=()=>applyTheme(b.dataset.t,true))}
let PLANS=null;try{PLANS=JSON.parse(localStorage.getItem('plans')||'null')}catch(e){}
