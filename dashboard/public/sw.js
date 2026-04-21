/* Service worker voor Panden Scanner PWA.
   Doel: app installeerbaar + offline fallback op laatste leads.json.
   Stale-while-revalidate: netwerk eerst voor verse data, cache als fallback. */

const CACHE = 'panden-scanner-v1';
const DATA_URL = 'https://raw.githubusercontent.com/clawtje94/panden-scanner/data/leads.json';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(['/']))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  // leads.json: netwerk-first, fallback cache (zodat je offline laatste data ziet)
  if (req.url.includes('leads.json')) {
    event.respondWith(
      fetch(req).then((r) => {
        const clone = r.clone();
        caches.open(CACHE).then((cache) => cache.put(req, clone));
        return r;
      }).catch(() => caches.match(req))
    );
    return;
  }
  // App-shell: cache-first
  if (req.mode === 'navigate' || req.destination === 'document') {
    event.respondWith(
      caches.match('/').then((cached) => cached || fetch(req))
    );
  }
});
