"""Independent evidence-first research agents. No network, LLM or order access."""
from decimal import Decimal
from datetime import date
from .market import INDEX

D=Decimal

def review(symbol,bars,*,mode,source):
    if mode not in ("synthetic","historical_unverified"):
        raise ValueError("Geçersiz veri modu.")
    n=len(bars)
    evidence={"symbol":symbol,"mode":mode,"source":source,"count":n,"last_session":bars[-1].get("session") if bars else None}
    agents=[]
    def add(role,status,summary,metrics=None):
        agents.append({"role":role,"status":status,"summary":summary,"metrics":metrics or {}})
    if n>=5:
        prices=[D(str(b["close"])) for b in bars]
        if any(not p.is_finite() or p<=0 for p in prices):raise ValueError("Geçersiz fiyat.")
        ma=sum(prices[-5:])/5
        delta=(prices[-1]/ma-1)*100
        total=(prices[-1]/prices[0]-1)*100
        peak=prices[0]; dd=D(0)
        for p in prices:
            peak=max(peak,p)
            dd=max(dd,(1-p/peak)*100)
        fmt=lambda x:str(x.quantize(D(".01")))
        add("Teknik analiz","hesaplandi","Son kapanış 5 gözlem ortalamasının "+("üzerinde." if delta>0 else "altında." if delta<0 else "seviyesinde."),{"ortalama":fmt(ma),"sapma_pct":fmt(delta),"donem_getirisi_pct":fmt(total)})
        add("Boğa görüşü","senaryo","Yukarı yönlü devam senaryosu ancak bağımsız veri ve ileri dönem testiyle değerlendirilebilir.",{"ortalama_uzerinde":delta>0})
        add("Ayı görüşü","senaryo","Geçmiş yükseliş gelecekteki getiriyi kanıtlamaz; düşüş ve likidite riski incelenmeli.",{"gozlenen_dusus_pct":fmt(dd)})
        add("Risk analizi","sinirli","Kapanış bazlı düşüş ölçüldü. Gün içi, likidite ve işlem maliyetleri bu ölçümde yok.",{"maks_dusus_pct":fmt(dd)})
    else:
        for role in ("Teknik analiz","Boğa görüşü","Ayı görüşü","Risk analizi"):
            add(role,"veri_yetersiz","En az 5 geçerli kapanış gözlemi gerekli.")
    add("Temel analiz","veri_yok","Finansal tablo, değerleme ve şirket verisi bağlı değil.")
    add("Haber analizi","veri_yok","Doğrulanmış haber kaynağı bağlı değil.")
    add("Makro analiz","veri_yok","Makroekonomik gözlem kaynağı bağlı değil.")
    add("Karar denetimi","arastirma","Ajanlar işlem kararı vermez. Eksik kanıtlar nedeniyle yatırım görüşü doğrulanmadı.")
    return {"evidence":evidence,"agents":agents,"verdict":"research_only","llm_enabled":False,"live_data_verified":False,"real_orders":False,"paper_orders_enabled":False}

def demo_review(symbol,tick):
    i=INDEX[symbol]
    return review(symbol,[{"close":str(p)} for p in i.prices[:tick+1]],mode="synthetic",source="Cyberbot sentetik seri")
