// Imported by the generated worker. API JSON is no longer runtime-cached;
// remove the previous worker's private responses when this worker activates.
self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((names) => Promise.all(
    names.filter((name) => /^api-reads(?:$|-)/.test(name)).map((name) => caches.delete(name)),
  )));
});
