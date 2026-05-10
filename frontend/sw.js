const CACHE = "guidance-v1";
const PRECACHE = ["/", "/index.html", "/style.css", "/camera.js", "/voice.js", "/navigation.js"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(PRECACHE))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  // Network-first for API calls; cache-first for static assets
  if (e.request.url.includes("/api/") || e.request.url.includes("/navigate") ||
      e.request.url.includes("/ws")) {
    return; // let browser handle API + WS
  }

  e.respondWith(
    caches.match(e.request).then((cached) => cached || fetch(e.request))
  );
});
