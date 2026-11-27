// Read-only structured research news view.
export function mountNewsView(root, request) {
  const section=document.createElement("section");
  const heading=document.createElement("h2");heading.textContent="Haberler";
  const filter=document.createElement("select");filter.setAttribute("aria-label","Haber önceliği");
  for(const [value,label] of [["low","Tüm öncelikler"],["medium","Orta ve üzeri"],["high","Yüksek"]]){
    const option=document.createElement("option");option.value=value;option.textContent=label;filter.append(option);
  }
  const market=document.createElement("select");market.setAttribute("aria-label","Piyasa");
  for(const [value,label] of [["","Tüm piyasalar"],["NASDAQ","NASDAQ"],["BIST","BIST"],["XETRA","Xetra"],["BINANCE_FUTURES","Binance Futures"],["SOLANA","Solana / DexTerm"],["GLOBAL","Küresel"]]){
    const option=document.createElement("option");option.value=value;option.textContent=label;market.append(option);
  }
  const symbol=document.createElement("input");symbol.type="search";symbol.maxLength=100;symbol.placeholder="Sembol (örn. AAPL, THYAO)";symbol.setAttribute("aria-label","Haber sembolü");
  const globalLabel=document.createElement("label");
  const globalNews=document.createElement("input");globalNews.type="checkbox";globalNews.checked=true;
  globalLabel.append(globalNews,document.createTextNode("Küresel haberleri dahil et"));
  const refresh=document.createElement("button");refresh.type="button";refresh.textContent="Yenile";
  const status=document.createElement("p");status.setAttribute("role","status");
  const list=document.createElement("div");
  section.append(heading,market,symbol,filter,globalLabel,refresh,status,list);root.replaceChildren(section);
  let items=[],disposed=false,controller;
  function render(){
    list.replaceChildren();
    for(const item of items){
      const card=document.createElement("article");
      const title=document.createElement("h3");title.textContent=item.title;
      const meta=document.createElement("p");
      const date=new Date(item.published_at);
      meta.textContent=String(item.source||"Kaynak belirtilmedi")+" · "+String(item.market||"—")+" · "+({low:"Düşük",medium:"Orta",high:"Yüksek"}[item.priority]||"—")+" · "+(Number.isFinite(date.getTime())?date.toLocaleString("tr-TR",{timeZone:"Europe/Istanbul"}):"—");
      const body=document.createElement("p");body.textContent=(item.summary_tr||"Türkçe özet henüz yok.")+"\nDoğrulanmamış araştırma haberi; işlem sinyali değildir.";body.style.whiteSpace="pre-wrap";
      card.append(title,meta,body);
      if(Array.isArray(item.symbols)&&item.symbols.length){const tags=document.createElement("p");tags.textContent="Semboller: "+item.symbols.join(", ");card.append(tags);}
      for(const line of [String(item.url||"")]){
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
      const params=new URLSearchParams({limit:"100",minimum:filter.value,include_global:String(market.value==="GLOBAL"||globalNews.checked)});
      if(market.value)params.append("market",market.value);
      if(symbol.value.trim())params.append("symbol",symbol.value.trim().toUpperCase());
      const response=await request("/api/research-news?"+params.toString(),{signal:current.signal,cache:"no-store"});
      if(!response.ok)throw new Error();
      const data=await response.json();
      if(disposed||controller!==current)return;
      items=Array.isArray(data.items)?data.items:[];render();
    }catch{if(!disposed&&controller===current){items=[];list.replaceChildren();status.textContent="Haberler alınamadı.";}}
    finally{clearTimeout(timeout);if(!disposed&&controller===current)refresh.disabled=false;}
  }
  filter.addEventListener("change",load);market.addEventListener("change",load);globalNews.addEventListener("change",load);symbol.addEventListener("change",load);symbol.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();load();}});refresh.addEventListener("click",load);load();
  return ()=>{disposed=true;controller?.abort();section.remove();};
}
