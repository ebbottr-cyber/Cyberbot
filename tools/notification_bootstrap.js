import {mountNotificationCenter} from "./notification_center_ui.js";
import {mountNotificationSettings} from "./notification_settings_ui.js";

// Host supplies authenticated, CSRF-aware same-origin request function.
// Existing service worker must import notification_push_worker.js.
export async function initializeNotifications({centerRoot,settingsRoot,request,publicKey,enabled=false}) {
  if (!enabled) return {enabled:false};
  if (!(centerRoot instanceof HTMLElement) || !(settingsRoot instanceof HTMLElement) || centerRoot===settingsRoot || typeof request!=="function") {
    throw new Error("Bildirim paneli bağlantıları eksik.");
  }
  await mountNotificationCenter(centerRoot,request);
  await mountNotificationSettings(settingsRoot,request,publicKey);
  const registration = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : null;
  return {enabled:true,secure:window.isSecureContext,workerActive:Boolean(registration?.active)};
}
