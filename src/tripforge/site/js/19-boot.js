/* ---------- background refresh: weather 15 min, rate 30 min, flights 5 min, ledger 30 s, plans hourly; all re-run when the tab comes back ---------- */
setInterval(weather,15*60e3);setInterval(fx,30*60e3);setInterval(liveFlights,5*60e3);setInterval(syncLedger,30e3);setInterval(timeline,30*60e3);
setInterval(refreshDist,60e3);
loadPlans();setInterval(loadPlans,60*60e3);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){weather();fx();liveFlights();syncLedger();timeline()}});
if('serviceWorker'in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
chk('todo',TODO);chk('pack',PACK);
startLocation();
