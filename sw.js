const CACHE_NAME = 'dyrexr-cache-v1';
const urlsToCache = [
  './index.html',
  './manifest.json'
];

// تثبيت ملفات التطبيق
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

// تشغيل التطبيق بسرعة
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        return response || fetch(event.request);
      })
  );
});