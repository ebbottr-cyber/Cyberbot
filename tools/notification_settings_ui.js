import {enableNotificationPush} from "./notification_push_client.js";

const categories = {news:"Haberler",market:"Piyasalar",trade:"İşlemler",risk:"Risk",ai:"Yapay zekâ",data:"Veri merkezi",system:"Sistem",github:"GitHub"};
const endpoint = "/api/notifications/preferences";

export async function mountNotificationSettings(root, request, publicKey) {
  const el = (tag, text) => { const node = document.createElement(tag); if(text) node.textContent=text; return node; };
  const response = await request(endpoint);
  if (!response.ok) throw new Error("Ayarlar yüklenemedi.");
  const settings = await response.json();
  const form = el("form"), status = el("p");
  status.setAttribute("role","status");
  const field = (label, type, value) => {
    const wrap=el("label",label+" "), input=el("input");
    input.type=type;
    if(type==="checkbox") input.checked=value; else input.value=value;
    input.required=type==="time";
    wrap.append(input); form.append(wrap,el("br")); return input;
  };
  const start=field("Sessiz saat başlangıcı","time",settings.quiet_start);
  const end=field("Sessiz saat bitişi","time",settings.quiet_end);
  const enabled=field("Genel telefon bildirimleri","checkbox",settings.push_enabled);
  const controls=Object.entries(categories).map(([key,label])=>[key,field(label,"checkbox",!settings.muted.includes(key))]);
  const save=el("button","Ayarları kaydet"); save.type="submit"; form.append(save);
  const device=el("p"), subscribe=el("button","Bu cihazda bildirim izni ver"), unsubscribe=el("button","Bu cihazın aboneliğini kaldır");
  subscribe.type=unsubscribe.type="button";
  const supported=window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  async function current() {
    const registration=await navigator.serviceWorker.getRegistration();
    return registration ? registration.pushManager.getSubscription() : null;
  }
  async function refresh() {
    if(!supported) {device.textContent="HTTPS ve Web Push destekli PWA gerekli. iPhone'da ana ekrana ekleyerek açın."; subscribe.disabled=unsubscribe.disabled=true; return;}
    const sub=await current();
    device.textContent="Cihaz izni: "+({granted:"Verildi",denied:"Reddedildi",default:"Bekliyor"}[Notification.permission])+" · "+(sub?"Yerel abonelik mevcut":"Abonelik yok");
    subscribe.disabled=Notification.permission==="denied" || !publicKey;
    unsubscribe.disabled=!sub;
  }
  form.addEventListener("submit",async event=>{
    event.preventDefault(); save.disabled=true;
    try {
      const res=await request(endpoint,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({quiet_start:start.value,quiet_end:end.value,push_enabled:enabled.checked,muted:controls.filter(([,input])=>!input.checked).map(([key])=>key)})});
      if(!res.ok) throw new Error();
      status.textContent="Ayarlar kaydedildi.";
    } catch {status.textContent="Ayarlar kaydedilemedi.";} finally {save.disabled=false;}
  });
  async function action(button, fn) {
    subscribe.disabled=unsubscribe.disabled=true;
    try {await fn();} catch {status.textContent="Abonelik işlemi başarısız. İzinleri ve bağlantıyı kontrol edin.";}
    finally {try {await refresh();} catch {status.textContent="Cihaz durumu okunamadı.";}}
  }
  subscribe.onclick=()=>action(subscribe,async()=>{await enableNotificationPush(request,publicKey);status.textContent="Cihaz aboneliği sunucuya kaydedildi.";});
  unsubscribe.onclick=()=>action(unsubscribe,async()=>{
    const sub=await current(); if(!sub)return;
    const res=await request("/api/notifications/push/subscriptions",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify(sub.toJSON())});
    if(!res.ok)throw new Error();
    if(!await sub.unsubscribe())throw new Error();
    status.textContent="Bu cihazın aboneliği kaldırıldı.";
  });
  root.replaceChildren(el("h2","Bildirim ayarları"),form,device,subscribe,unsubscribe,status);
  await refresh();
}
