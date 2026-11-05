/* ---------- shared state + helpers every module may use. Trip values live in 03-data-trip / 04-data-kit. ---------- */
let ROLE=localStorage.getItem('role')||'member';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
