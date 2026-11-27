import {mountNewsView} from "./notification_news_ui.js";
import {mountNotificationCenter} from "./notification_center_ui.js";
import {mountNotificationHealth} from "./notification_health_ui.js";
import {mountNotificationSettings} from "./notification_settings_ui.js";

// Host supplies authenticated, CSRF-aware same-origin request function.
// Existing service worker must import notification_push_worker.js.
export async function initializeNotifications({centerRoot,settingsRoot,healthRoot=null,newsRoot=null,request,publicKey,enabled=false}) {
  if (!enabled) return {enabled:false};
  if (!(centerRoot instanceof HTMLElement) || !(settingsRoot instanceof HTMLElement) || centerRoot===settingsRoot || typeof request!=="function") {
    throw new Error("Bildirim paneli bağlantıları eksik.");
  }
  if (healthRoot !== null && (!(healthRoot instanceof HTMLElement) || healthRoot===centerRoot || healthRoot===settingsRoot)) throw new Error("Sağlık ekranı bağlantısı geçersiz.");
  if (newsRoot !== null && (!(newsRoot instanceof HTMLElement) || [centerRoot,settingsRoot,healthRoot].some(root=>root && (root===newsRoot || root.contains(newsRoot) || newsRoot.contains(root))))) throw new Error("Haberler ekranı bağlantısı geçersiz.");
  await mountNotificationCenter(centerRoot,request);
  await mountNotificationSettings(settingsRoot,request,publicKey);
  const registration = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : null;
  const disposeHealth = healthRoot ? mountNotificationHealth(healthRoot,request) : ()=>{};
  const disposeNews = newsRoot ? mountNewsView(newsRoot,request) : ()=>{};
  return {disposeHealth,disposeNews,enabled:true,secure:window.isSecureContext,workerActive:Boolean(registration?.active)};
}
