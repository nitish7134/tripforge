// Offline cache for the trip page: network first, fall back to the last good copy.
// The deploy bumps the number in C on every ship; a stale C keeps serving the old page on phones that have it.
const C = 'trip-v1';
const FILES = ['./', './index.html', './manifest.webmanifest', './icon.svg', './data/plans.json'];
self.addEventListener('install', e => e.waitUntil(caches.open(C).then(c => c.addAll(FILES.filter(Boolean)).catch(() => {})).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(fetch(e.request).then(r => { const cp = r.clone(); caches.open(C).then(c => c.put(e.request, cp)); return r; })
    .catch(() => caches.match(e.request).then(m => m || caches.match('./index.html'))));
});
