/**
 * Service Worker — PWA offline support.
 */

// TODO: Implement:
//   - Cache static assets (app shell)
//   - Network-first for API calls
//   - Offline fallback page
//   - Push notification handling

const CACHE_NAME = 'omni-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Network-first strategy
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
