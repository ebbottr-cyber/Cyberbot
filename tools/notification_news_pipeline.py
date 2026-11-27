"""Explicit research ingestion pipeline; caller supplies source records."""
import hashlib
from tools.notification_ai_adapter import enrich_news
from tools.notification_news_filter import MARKETS

def process_news(news_store, record, *, provider=None, ai_enabled=False, enabled=False, symbol_aliases=None):
    if not enabled:
        return {"status":"disabled"}
    for field in ("title","source","url","published_at","source_id"):
        if not isinstance(record.get(field),str) or not record[field].strip() or len(record[field])>4096:
            raise ValueError("Invalid source record")
    summary=record.get("summary","")
    if not isinstance(summary,str) or len(summary)>20000:
        raise ValueError("Invalid source summary")
    market=record.get("market")
    if market is not None and market not in MARKETS:
        raise ValueError("Invalid market")
    key=hashlib.sha256((record["source"].upper()+":"+record["source_id"]).encode()).hexdigest()
    analysis=enrich_news(record["title"],summary,record["source"],provider,enabled=ai_enabled,symbol_aliases=symbol_aliases)
    candidates=analysis["candidate_markets"]
    if market is None:
        market=candidates[0] if len(candidates)==1 and candidates[0] in MARKETS else "GLOBAL"
    article={"event_key":"research:"+key,"title":record["title"],"source":record["source"],
             "url":record["url"],"published_at":record["published_at"],"market":market,
             "priority":analysis["priority"],"symbols":analysis["candidate_symbols"],
             "topics":analysis["topics"],"summary_tr":analysis["summary_tr"] or ""}
    saved=news_store.save(article)
    return {"status":"saved" if saved else "duplicate","event_key":article["event_key"],
            "ai_status":analysis["ai_status"],"research_only":True,"orders_enabled":False}
