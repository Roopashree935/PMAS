/* ═══════════════════════════════════════════════════════════════
   PMAS Demo — Service Worker (sw.js)
   Makes the demo app installable and works offline.
   Cache-first strategy for app shell.
   ═══════════════════════════════════════════════════════════════ */
const CACHE_NAME = 'pmas-demo_v4';
const APP_SHELL = [
  './',
  './index.html',
  './css/styles.css',
  './js/i18n.js',
  './js/db.js',
  './js/adherence.js',
  './js/reminders.js',
  './js/export.js',
  './js/app.js',
  './manifest.json',
  '../assets/images/favicon/favicon.png'
];

/* Install: pre-cache app shell */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
      .catch(err => console.warn('SW cache error:', err))
  );
});

/* Activate: clean old caches */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

/* Fetch: cache-first for app shell, network fallback */
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(event.request)
      .then((cached) => {
        if (cached) return cached;
        return fetch(event.request)
          .then((response) => {
            if (response.ok && response.type === 'basic') {
              const clone = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
            return response;
          })
          .catch(() => {
            if (event.request.mode === 'navigate') {
              return caches.match('./index.html');
            }
          });
      })
  );
});
