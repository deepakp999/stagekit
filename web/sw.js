// App shell cached for offline use on stage. Song data: network first, cached copy if offline.
const SHELL = "stagekit-shell-v13";
const DATA = "stagekit-data-v1";
const FILES = ["./", "index.html", "styles.css", "app.js", "tabla.js", "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => ![SHELL, DATA].includes(k)).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.includes("/api/")) {
    // Audio is too big to cache; only JSON (songs, set lists) is kept for offline live mode.
    if (/\.(mp3|wav|zip)$/.test(url.pathname)) return;
    e.respondWith(
      fetch(e.request).then(r => {
        if (r.ok) { const copy = r.clone(); caches.open(DATA).then(c => c.put(e.request, copy)); }
        return r;
      }).catch(() => caches.match(e.request).then(r => r || new Response('{"offline":true}', {status: 503, headers: {"Content-Type": "application/json"}})))
    );
    return;
  }
  // App files: network first so updates arrive immediately; cached copy when offline.
  e.respondWith(
    fetch(e.request, {cache: "no-cache"}).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(SHELL).then(c => c.put(e.request, copy)); }
      return r;
    }).catch(() => caches.match(e.request).then(r => r || caches.match("index.html")))
  );
});
