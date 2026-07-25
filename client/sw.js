/* Service worker — PWA installable + offline (brief §4).
   Coquille applicative (HTML/JS/CSS) en NETWORK-FIRST : on récupère toujours la
   dernière version en ligne, le cache ne sert que de secours hors-ligne. Ainsi les
   mises à jour se propagent sans rester bloquées sur une version périmée.
   Ressources immuables (vendor, icônes) en CACHE-FIRST. /api et /ws jamais mis en cache. */
const CACHE = 'proximo-v2';
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

function isShell(url, req) {
  if (req.mode === 'navigate') return true;
  return ['/', '/index.html', '/app.js', '/styles.css'].includes(url.pathname)
      || url.pathname.endsWith('.webmanifest');
}

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')) return;

  if (isShell(url, e.request)) {
    // Network-first : dernière version en ligne, secours cache si hors-ligne.
    e.respondWith(
      fetch(e.request).then((res) => {
        const copy = res.clone();
        if (res.ok) caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      }).catch(() => caches.match(e.request).then((hit) => hit || caches.match('/index.html')))
    );
    return;
  }
  // Cache-first pour le reste (vendor, icônes).
  e.respondWith(
    caches.match(e.request).then((hit) =>
      hit || fetch(e.request).then((res) => {
        const copy = res.clone();
        if (res.ok && res.type === 'basic') caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      })
    )
  );
});
