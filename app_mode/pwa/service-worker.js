const CACHE_NAME = "solar-dashboard-v2";
const APP_SHELL = [
    "/",
    "/manifest.webmanifest",
    "/static/css/dashboard.css",
    "/static/js/dashboard.js",
    "/app-assets/pwa.css",
    "/app-assets/pwa.js",
    "/app-assets/offline.html",
    "/app-assets/icons/icon-192.png",
    "/app-assets/icons/icon-512.png",
    "/app-assets/icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((keys) => Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET") return;

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;
    if (url.pathname === "/data" || url.pathname.startsWith("/history/")) return;

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put("/", copy));
                    return response;
                })
                .catch(async () => (
                    await caches.match("/")
                    || await caches.match("/app-assets/offline.html")
                ))
        );
        return;
    }

    event.respondWith(
        caches.match(request).then((cached) => {
            const refreshed = fetch(request)
                .then((response) => {
                    if (response.ok) {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                    }
                    return response;
                })
                .catch(() => cached);
            return cached || refreshed;
        })
    );
});
