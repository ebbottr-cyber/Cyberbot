// Requires existing same-origin service worker and authenticated API.
export async function enableNotificationPush(request, publicKey) {
  if (!window.isSecureContext || !("serviceWorker" in navigator) ||
      !("PushManager" in window) || !("Notification" in window)) {
    throw new Error("HTTPS ve Web Push destekli PWA gerekli.");
  }
  const registration = await navigator.serviceWorker.getRegistration();
  if (!registration || !registration.active) throw new Error("Aktif Service Worker gerekli.");
  if (await Notification.requestPermission() !== "granted") {
    throw new Error("Bildirim izni verilmedi.");
  }
  const key = Uint8Array.from(atob(publicKey.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(publicKey.length / 4) * 4, "=")), c => c.charCodeAt(0));
  if (key.length !== 65 || key[0] !== 4) throw new Error("Geçersiz VAPID anahtarı.");
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) subscription = await registration.pushManager.subscribe({userVisibleOnly:true, applicationServerKey:key});
  const response = await request("/api/notifications/push/subscriptions", {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(subscription.toJSON())
  });
  if (!response.ok) throw new Error("Sunucu aboneliği kaydedemedi.");
  return true;
}
