// Read-only news view. Existing inbox records do not contain structured AI metadata.
export function mountNewsView(root, request) {
  const section=document.createElement("section");
  const heading=document.createElement("h2");heading.textContent="Haberler";
  const filter=document.createElement("select");filter.setAttribute("aria-label","Haber önceliği");
  for(const [value,label] of [["all","Tümü"],["info","Normal"],["warning","Yüksek"],["critical","Kritik"]]){
    const option=document.createElement("option");option.value=value;option.textContent=label;filter.append(option);
  }
  const refresh=document.createElement("button");refresh.type="button";refresh.textContent="Yenile";
  const status=document.createElement("p");status.setAttribute("role","status");
  const list=document.createElement("div");
  section.append(heading,filter,refresh,status,list);root.replaceChildren(section);
  let items=[],disposed=false,controller;
  function render(){
    list.replaceChildren();
    for(const item of items.filter(x=>filter.value==="all"||x.severity===filter.value)){
      const card=document.createElement("article");
      const title=document.createElement("h3");title.textContent=item.title;
      const meta=document.createElement("p");
      const date=new Date(item.created_at);
      meta.textContent=String(item.source||"Kaynak belirtilmedi")+" · "+(Number.isFinite(date.getTime())?date.toLocaleString("tr-TR",{timeZone:"Europe/Istanbul"}):"—");
      const body=document.createElement("p");body.textContent=item.body;body.style.whiteSpace="pre-wrap";
      card.append(title,meta,body);
      for(const line of String(item.body||"").split("\n")){
        try{
          const url=new URL(line.trim());
          if(url.protocol!=="https:"||url.username||url.password)continue;
          const link=document.createElement("a");link.href=url.href;link.textContent="Kaynağı aç: "+url.hostname;link.target="_blank";link.rel="noopener noreferrer";card.append(link);
        }catch{}
      }
      list.append(card);
    }
    if(!list.childElementCount)status.textContent="Bu filtreye uygun haber yok.";
    else status.textContent=list.childElementCount+" haber gösteriliyor.";
  }
  async function load(){
    if(disposed)return;
    controller?.abort();const current=new AbortController();controller=current;
    refresh.disabled=true;status.textContent="Haberler yükleniyor…";
    const timeout=setTimeout(()=>current.abort(),10000);
    try{
      const response=await request("/api/notifications?category=news&limit=100",{signal:current.signal,cache:"no-store"});
      if(!response.ok)throw new Error();
      const data=await response.json();
      if(disposed||controller!==current)return;
      items=Array.isArray(data.items)?data.items:[];render();
    }catch{if(!disposed&&controller===current){items=[];list.replaceChildren();status.textContent="Haberler alınamadı.";}}
    finally{clearTimeout(timeout);if(!disposed&&controller===current)refresh.disabled=false;}
  }
  filter.addEventListener("change",render);refresh.addEventListener("click",load);load();
  return ()=>{disposed=true;controller?.abort();section.remove();};
}
