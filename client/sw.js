/* Service worker — app shell offline (PWA installable, brief §4).
   Stratégie : cache-first pour la coquille statique, réseau direct pour /api et /ws. */
const CACHE = 'proximo-v1';
const SHELL = [
  '/', '/index.html', '/app.js', '/styles.css', '/manifest.webmanifest',
  '/vendor/preact-standalone.module.js',
  '/icons/icon-192.png', '/icons/icon-512.png', '/icons/icon-maskable-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  // Ne jamais mettre en cache l'API, le WebSocket ou les QR (données vivantes).
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')) return;
  e.respondWith(
    caches.match(e.request).then((hit) =>
      hit || fetch(e.request).then((res) => {
        const copy = res.clone();
        if (res.ok && res.type === 'basic') {
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      }).catch(() => caches.match('/index.html'))
    )
  );
});
