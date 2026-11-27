import {mountNotificationCenter} from "./notification_center_ui.js";
import {mountNotificationHealth} from "./notification_health_ui.js";
import {mountNotificationSettings} from "./notification_settings_ui.js";

// Host supplies authenticated, CSRF-aware same-origin request function.
// Existing service worker must import notification_push_worker.js.
export async function initializeNotifications({centerRoot,settingsRoot,healthRoot=null,request,publicKey,enabled=false}) {
  if (!enabled) return {enabled:false};
  if (!(centerRoot instanceof HTMLElement) || !(settingsRoot instanceof HTMLElement) || centerRoot===settingsRoot || typeof request!=="function") {
    throw new Error("Bildirim paneli bağlantıları eksik.");
  }
  if (healthRoot !== null && (!(healthRoot instanceof HTMLElement) || healthRoot===centerRoot || healthRoot===settingsRoot)) throw new Error("Sağlık ekranı bağlantısı geçersiz.");
  await mountNotificationCenter(centerRoot,request);
  await mountNotificationSettings(settingsRoot,request,publicKey);
  const registration = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : null;
  const disposeHealth = healthRoot ? mountNotificationHealth(healthRoot,request) : ()=>{};
  return {disposeHealth,enabled:true,secure:window.isSecureContext,workerActive:Boolean(registration?.active)};
}
