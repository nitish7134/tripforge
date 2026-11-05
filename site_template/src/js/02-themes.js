/* ---------- themes: accent + decoration + stickers + PG filter. Visitors are pinned to VISITOR_THEME. ----------
   A theme answers four questions: accent [--mari, --mari-ink], deco (up to 4 glyphs tiled in the margins),
   stk (up to 3 glyphs stuck on each page photo), pg (true drops kind:party options, late slots and .adult blocks). */
const tile=e=>e.length?`url("data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><text x='18' y='64' font-size='42' transform='rotate(-16 18 64)'>${e[0]}</text><text x='140' y='96' font-size='34' transform='rotate(18 140 96)'>${e[1]||e[0]}</text><text x='56' y='186' font-size='38' transform='rotate(9 56 186)'>${e[2]||e[0]}</text><text x='170' y='214' font-size='30' transform='rotate(-24 170 214)'>${e[3]||e[1]||e[0]}</text></svg>`)}")`:'none';
const THEMES={
 party:{name:'Party',accent:['#ffb020','#1a1200'],deco:['🍃','🍺','🔥','🥃'],stk:['🍺','🔥'],pg:false},
 'party-drinks':{name:'Drinks',accent:['#ffc93c','#1a1200'],deco:['🍺','🥃','🍹','🍾'],stk:['🍺','🥃','🎉'],pg:false},
 birthday:{name:'Birthday',accent:['#ff7ab6','#2a0a19'],deco:['🎂','🎈','🥤','🎁'],stk:['🎂','🎈'],pg:true},
 pg13:{name:'Calm',accent:['#35d0b8','#06211c'],deco:['🌊','🐚','🌞','🍹'],stk:['🌴','🌊'],pg:true},
 plain:{name:'Plain',accent:['#ffb020','#1a1200'],deco:[],stk:[],pg:false}};
const VISITOR_THEME='pg13';
let THEME=THEMES.plain;
function applyTheme(n,save){if(!THEMES[n])n='plain';THEME=THEMES[n];const r=document.documentElement;r.dataset.theme=n;r.classList.toggle('pgmode',!!THEME.pg);r.style.setProperty('--deco',tile(THEME.deco));
 if(THEME.accent){r.style.setProperty('--mari',THEME.accent[0]);r.style.setProperty('--mari-ink',THEME.accent[1])}
 if(save)localStorage.setItem('theme',n);document.querySelectorAll('#themes button').forEach(b=>b.classList.toggle('on',b.dataset.t===n));if(typeof timeline==='function')timeline()}
function stickers(){return THEME.stk.length?`<span class="stk">${THEME.stk.join('')}</span>`:''}
function themePicker(){const box=document.getElementById('themebox');if(ROLE==='visitor'){box.hidden=true;return}box.hidden=false;
 document.getElementById('themes').innerHTML=Object.entries(THEMES).map(([k,t])=>`<button data-t="${k}" class="${THEME===t?'on':''}">${t.stk[0]||'◻'} ${t.name}</button>`).join('');
 document.querySelectorAll('#themes button').forEach(b=>b.onclick=()=>applyTheme(b.dataset.t,true))}

let PLANS=null;try{PLANS=JSON.parse(localStorage.getItem('plans')||'null')}catch(e){}
