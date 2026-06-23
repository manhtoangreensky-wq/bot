const TOAN_AAS_CACHE = "toan-aas-onboarding-v1";
const TOAN_AAS_STATIC = [
  "/onboarding",
  "/manifest.webmanifest",
  "/logo.png?v=20260619"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(TOAN_AAS_CACHE).then((cache) => cache.addAll(TOAN_AAS_STATIC)).catch(() => undefined)
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== TOAN_AAS_CACHE).map((key) => caches.delete(key))
    ))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request).then((response) => {
      const clone = response.clone();
      caches.open(TOAN_AAS_CACHE).then((cache) => cache.put(event.request, clone)).catch(() => undefined);
      return response;
    }).catch(() => caches.match(event.request))
  );
});
