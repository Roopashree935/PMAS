/* ═══════════════════════════════════════════════════════════════
   PMAS Platform — Service Worker (sw.js)
   PWA offline capability for the platform site itself.
   Caches app shell and serves from cache when offline.
   ═══════════════════════════════════════════════════════════════ */
const CACHE_NAME = 'pmas-platform_v6';
const APP_SHELL = [
  './',
  './/index.html',
  './/about.html',
  './/contact.html',
  './/privacy.html',
  './/terms.html',
  './/404.html',
  './/assets/css/style.css',
  './/assets/css/components.css',
  './/assets/css/utilities.css',
  './/assets/css/animations.css',
  './/assets/js/main.js',
  './/assets/js/navigation.js',
  './/assets/js/theme.js',
  './/assets/js/animations.js',
  './/assets/images/favicon/favicon.png',
  './/manifest.json'
];

/* ── Install: pre-cache app shell ─────────────────────────── */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

/* ── Activate: clean old caches ───────────────────────────── */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

/* ── Fetch: cache-first for app shell, network-first for rest ─ */
self.addEventListener('fetch', (event) => {
  // Skip non-GET requests
  if (event.request.method !== 'GET') return;

  // Skip cross-origin requests
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  // Cache-first for app shell assets
  event.respondWith(
    caches.match(event.request)
      .then((cached) => {
        if (cached) return cached;
        // Not in cache — fetch, cache, return
        return fetch(event.request)
          .then((response) => {
            // Only cache same-origin successful responses
            if (response.ok && response.type === 'basic') {
              const clone = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
            return response;
          })
          .catch(() => {
            // Offline fallback — serve 404 page for navigations
            if (event.request.mode === 'navigate') {
              return caches.match('./404.html');
            }
          });
      })
  );
});
