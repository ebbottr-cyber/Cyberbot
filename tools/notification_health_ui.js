const states={ok:"Çalışıyor",degraded:"Kısmi hata",error:"Hata",stale:"Güncelleme gecikti",unknown:"Bilinmiyor",disabled:"Kapalı"};
export function mountNotificationHealth(root,request,{interval=30000}={}) {
  if (!Number.isFinite(interval)||interval<15000||interval>300000) throw new Error("Geçersiz yenileme aralığı");
  const section=document.createElement("section");
  const heading=document.createElement("h2"); heading.textContent="Bildirim sistemi sağlığı";
  const status=document.createElement("p"); status.setAttribute("role","status");
  const metrics=document.createElement("dl");
  const note=document.createElement("p"); note.textContent="Sunucu kabulü, telefonda teslim edildiğini kanıtlamaz.";
  section.append(heading,status,metrics,note); root.replaceChildren(section);
  let stopped=false, timer, controller;
  async function refresh(){
    if(stopped)return;
    if(document.hidden){timer=setTimeout(refresh,interval);return;}
    controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),10000);
    try {
      const response=await request("/api/notifications/health",{signal:controller.signal,cache:"no-store"});
      if(!response.ok)throw new Error();
      const data=await response.json();
      if(stopped)return;
      status.textContent=states[data.worker.status]||"Bilinmiyor";
      const date=new Date(data.worker.finished_at||NaN);
      const values=[["Bekleyen",data.queue.pending],["Sunucu kabulü",data.queue.accepted],["Başarısız",data.queue.failed],["Süresi dolan",data.queue.expired],["Kayıtlı cihazlar",data.subscriptions],["Son kontrol",Number.isFinite(date.getTime())?date.toLocaleString("tr-TR",{timeZone:"Europe/Istanbul"}):"—"]];
      metrics.replaceChildren();
      for(const [label,value] of values){const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=String(value??"—");metrics.append(dt,dd);}
    }catch{if(!stopped){status.textContent="Sağlık verisine erişilemiyor.";metrics.replaceChildren();}}
    finally{clearTimeout(timeout);if(!stopped)timer=setTimeout(refresh,interval);}
  }
  refresh();
  return ()=>{stopped=true;clearTimeout(timer);controller?.abort();section.remove();};
}
