const CACHE = 'finance-mobile-v1';
const STATIC = [
  '/mobile/index.html',
  '/mobile/transactions.html',
  '/mobile/add.html',
  '/mobile/accounts.html',
  '/mobile/app.js',
  '/mobile/style.css',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(STATIC)));
});

self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('/api/')) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
