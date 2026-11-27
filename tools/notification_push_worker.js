// Import into the existing service worker; do not register a competing worker.
self.addEventListener("push", event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch {}
  if (!data || typeof data !== "object") data = {};
  const title = typeof data.title === "string" ? data.title.slice(0, 120) : "Cyberbot";
  const body = typeof data.body === "string" ? data.body.slice(0, 240) : "Yeni bildiriminiz var.";
  event.waitUntil(self.registration.showNotification(title, {
    body, tag: typeof data.id === "string" ? "cyberbot-" + data.id.slice(0, 100) : "cyberbot",
    data: {url: self.registration.scope}
  }));
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil((async () => {
    const target = self.registration.scope;
    const windows = await self.clients.matchAll({type:"window", includeUncontrolled:true});
    const existing = windows.find(client => client.url.startsWith(target));
    if (existing) return existing.focus();
    return self.clients.openWindow(target);
  })());
});
