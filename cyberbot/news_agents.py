"""Evidence-first news research roles and optional constrained local-model checklist."""
import json,os,re
from datetime import datetime,timezone
import httpx
from .news_graph import rows,links_for,TOPICS,NAMES
from .news_feed import FEEDS
from .news_impact import stamp
from .news_memory import overview

VERSION="news-agents-1"
CHECKS={
    "source":"Asıl duyuru ve yayın zamanı doğrulanmalı.",
    "scope":"Varlığın duyuru ile ilişkisi bağımsız kaynaktan doğrulanmalı.",
    "data":"İzinli fiyat verisi, seans ve ölçüm zamanları kontrol edilmeli.",
    "context":"Beklentiler, önceki açıklamalar ve eş zamanlı olaylar incelenmeli.",
    "baseline":"Karşılaştırma endeksi ve işlem maliyetleri incelenmeli.",
}
PRIORITY={"monetary_policy":"high","financial_stability":"high","regulation":"high","inflation":"review","company":"review","exchange":"review","ecosystem":"review","macro":"review"}
class AgentError(ValueError):pass

def assess(event,links,memory,*,now):
    topic=event.get("category",event["kind"])
    is_calendar=event["event_type"]=="calendar"
    official=event.get("origin")=="rss" and event.get("source_id") in FEEDS
    event_at=stamp(event["event_at"]);recorded=stamp(event["recorded_at"])
    assets=sorted({(x["market"],x["symbol"]) for x in links if x["record_key"]==event["record_key"]})
    # Only count descriptive groups for explicitly asserted asset, not all market-wide results.
    matches=[g for g in memory.get("groups",[]) if (g["market"],g["symbol"]) in assets and g["category"]==topic and g.get("statistics") is not None]
    roles=[
        {"id":"source","status":"official_feed_origin" if official else "manual_unverified","summary":"Resmî akış kökeni kayıtlı; haber içeriği bağımsız doğrulanmadı." if official else "Operatör referansı; kaynak ve içerik doğrulanmadı."},
        {"id":"priority","status":PRIORITY.get(topic,"unclassified"),"summary":"Kategoriye göre inceleme önceliği; fiyat etkisinin büyüklüğü veya yönü değildir."},
        {"id":"scope","status":"operator_asserted" if assets else "missing","summary":"Varlık ilişkileri operatör beyanı; ihraççı/işlem yeri doğrulanmadı." if assets else "Varlık eşleşmesi yok; piyasa kapsamı tek başına maruziyet kanıtı değil."},
        {"id":"timing","status":"scheduled" if is_calendar and event_at>now else "calendar_unconfirmed" if is_calendar else "recorded","summary":"Takvim kaydı gerçekleşmiş olay değildir." if is_calendar else "Yayın zamanı ile ilk kayıt zamanı ayrıdır."},
        {"id":"history","status":"descriptive_context" if matches and not is_calendar else "insufficient","summary":"Geçmiş kategori grupları mevcut; güncel olaya ileri tahmin olarak kullanılamaz." if matches and not is_calendar else "Bu kapsamda uygun betimsel bağlam yok."},
        {"id":"scenarios","status":"hypotheses_only","summary":"Yukarı, aşağı veya sınırlı tepki senaryoları araştırılabilir; olasılık, yön veya hedef fiyat hesaplanmadı."},
        {"id":"risk","status":"research_only","summary":"Kaynak, varlık, karşılaştırma ve fiyat doğrulaması eksik. Emir veya strateji terfisi yok."}
    ]
    return {"version":VERSION,"record_key":event["record_key"],"label":event["label"],"url":event["url"],"category":topic,"market":event["market"],"event_type":event["event_type"],"event_at":event["event_at"],"recorded_at":event["recorded_at"],
            "record_delay_seconds":max(0,int((recorded-event_at).total_seconds())) if not is_calendar else None,
            "agents":roles,"assets":[{"market":m,"symbol":s,"verified":False} for m,s in assets],
            "descriptive_group_count":len(matches) if not is_calendar else 0,
            "strategy_hypotheses":[NAMES[k] for k in TOPICS.get(topic,())] if not is_calendar else [],
            "checklist":[{"id":k,"text":v} for k,v in CHECKS.items()],
            "llm_used":False,"source_verified":False,"sentiment":"not_assessed","direction_prediction":None,"causal_impact_verified":False,
            "real_orders":False,"promotion_enabled":False}

def review(record_key):
    if not re.fullmatch(r"(manual|rss):[0-9a-f]{64}",record_key):raise AgentError("Haber kimliği geçersiz.")
    event=next((e for e in rows() if e["record_key"]==record_key),None)
    if event is None:raise AgentError("Görünür haber kaydı bulunamadı.")
    return assess(event,links_for([record_key]),overview(),now=datetime.now(timezone.utc))

def local_checklist(report,model,*,transport=None):
    if not isinstance(model,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}",model):raise AgentError("Yerel model adı geçersiz.")
    # No publisher text, URLs, symbols, notes, credentials or raw prices in prompt.
    # Model can only reorder predefined checks; never create conclusions or instructions.
    allowed_statuses={"official_feed_origin","manual_unverified","high","review","unclassified","operator_asserted","missing","scheduled","calendar_unconfirmed","recorded","descriptive_context","insufficient","hypotheses_only","research_only"}
    state=[{"role":x["id"],"status":x["status"]} for x in report["agents"] if x["id"] in ("source","priority","scope","timing","history","scenarios","risk") and x["status"] in allowed_statuses]
    prompt="Reorder the five research checklist IDs by review priority. Return JSON object with only order, a permutation of source,scope,data,context,baseline. Do not add conclusions. Status metadata: "+json.dumps(state)
    payload={"model":model,"prompt":prompt,"stream":False,"format":"json","options":{"temperature":0,"num_predict":96}}
    try:
        if transport is not None:d=transport(payload)
        else:
            with httpx.Client(timeout=httpx.Timeout(45,connect=3),follow_redirects=False,trust_env=False) as client:
                with client.stream("POST","http://127.0.0.1:11434/api/generate",json=payload) as res:
                    res.raise_for_status()
                    raw=bytearray()
                    for chunk in res.iter_bytes():
                        raw.extend(chunk)
                        if len(raw)>32768:raise AgentError("Model yanıtı çok büyük.")
                    d=json.loads(raw)
        if not isinstance(d,dict) or not isinstance(d.get("response"),str) or len(d["response"])>2048:raise ValueError()
        x=json.loads(d["response"]);order=x.get("order") if isinstance(x,dict) else None
        if not isinstance(x,dict) or set(x)!={"order"} or not isinstance(order,list) or len(order)!=len(CHECKS) or any(not isinstance(k,str) for k in order) or set(order)!=set(CHECKS):raise ValueError()
        return {"model":model,"checklist":[{"id":k,"text":CHECKS[k]} for k in order],"output_validated":True,"financial_conclusions_verified":False,"real_orders":False}
    except (ValueError,TypeError,httpx.HTTPError):raise AgentError("Yerel model yanıtı geçersiz veya erişilemedi.") from None
