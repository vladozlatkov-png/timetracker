const CACHE = 'timetracker-v2-realization';
const FILES = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-192.svg',
  '/icon-512.svg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Never cache the sync API — always network
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(e.request));
    return;
  }
  e.respondWith(
    caches.match(e.request).then(
      (cached) =>
        cached ||
        fetch(e.request).catch(() => caches.match('/index.html'))
    )
  );
});

// Allow the page to ask the SW to nudge a sync when back online
self.addEventListener('message', (e) => {
  if (e.data && e.data.type === 'FLUSH_SYNC') {
    self.clients.matchAll().then((clients) => {
      clients.forEach((c) => c.postMessage({ type: 'FLUSH_SYNC' }));
    });
  }
});

self.addEventListener('sync', (e) => {
  if (e.tag === 'tt-sync') {
    e.waitUntil(
      self.clients.matchAll().then((clients) => {
        clients.forEach((c) => c.postMessage({ type: 'FLUSH_SYNC' }));
      })
    );
  }
});
