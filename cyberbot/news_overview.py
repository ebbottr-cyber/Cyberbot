"""Read-only dashboard snapshot of recorded news, calendar and research readiness."""
import json,os,sqlite3
from contextlib import closing
from datetime import datetime,timezone,timedelta
from .research_pipeline import research_path
from .news_feed import read as read_rss
from .news_agents import PRIORITY
from .news_impact import stamp
from .news_memory import overview as memory_overview

VERSION="news-overview-1"
STALE_SECONDS=1800

def manual_records(now):
    p=research_path()
    if not p.is_file():return [],[]
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='news_refs'").fetchone():return [],[]
        # Query nearest upcoming calendar separately: distant events cannot crowd out near ones.
        current=now.isoformat();recent=(now-timedelta(days=7)).isoformat();next_week=(now+timedelta(days=7)).isoformat()
        news=[json.loads(x[0]) for x in db.execute("SELECT payload FROM news_refs WHERE event_at>=? AND event_at<=? AND json_extract(payload,'$.event_type')='news' ORDER BY event_at DESC,id DESC LIMIT 100",(recent,current))]
        calendar=[json.loads(x[0]) for x in db.execute("SELECT payload FROM news_refs WHERE event_at>=? AND event_at<=? AND json_extract(payload,'$.event_type')='calendar' ORDER BY event_at ASC,id ASC LIMIT 20",(current,next_week))]
        return news,calendar

def assemble(manual,calendar,rss,memory,*,now,model_configured=False):
    feeds=[]
    for feed in rss["feeds"]:
        age=None
        if feed.get("last_success"):
            age=(now-stamp(feed["last_success"])).total_seconds()
        if not feed["enabled"]:status="disabled"
        elif feed["status"]=="failed":status="failed"
        elif feed["status"]=="attempted":status="refresh_pending"
        elif age is None:status="not_started"
        elif age<0 or age>STALE_SECONDS:status="stale"
        elif feed["status"]=="ok":status="recent_success"
        else:status="unknown"
        feeds.append({**feed,"dashboard_status":status,"age_seconds":int(age) if age is not None and age>=0 else None})
    records=[]
    for origin,items in (("manual",manual),("rss",rss["items"])):
        for x in items:
            when=stamp(x["event_at"])
            if x.get("event_type")!="news" or not now-timedelta(days=7)<=when<=now:continue
            topic=x.get("category",x["kind"])
            records.append({"record_key":origin+":"+x["id"],"label":x["label"],"market":x["market"],"url":x["url"],"source":x["source"],"event_at":when.isoformat(),"origin":origin,"category":topic,"review_priority":PRIORITY.get(topic,"unclassified")})
    # Deduplicate URLs only within market scope; keep earliest recorded publication time, then stable key.
    unique={}
    for x in sorted(records,key=lambda x:(x["event_at"],x["record_key"])):
        unique.setdefault((x["market"],x["url"]),x)
    records=sorted(unique.values(),key=lambda x:(x["event_at"],x["record_key"]),reverse=True)
    upcoming=[]
    for x in calendar:
        when=stamp(x["event_at"])
        if x.get("event_type")!="calendar" or not now<=when<=now+timedelta(days=7):continue
        upcoming.append({"label":x["label"],"url":x["url"],"market":x["market"],"event_at":when.isoformat(),"source":x["source"],"status":"manual_unverified","within_24h":when-now<=timedelta(days=1)})
    upcoming.sort(key=lambda x:x["event_at"])
    warnings=[]
    if not any(x["enabled"] for x in feeds):warnings.append({"code":"rss_disabled","text":"Otomatik RSS kaynakları kapalı."})
    for x in feeds:
        if x["enabled"] and x["dashboard_status"]!="recent_success":warnings.append({"code":"rss_"+x["dashboard_status"],"text":x["name"]+": güncel başarılı kaynak sorgusu doğrulanmadı."})
    if not upcoming:warnings.append({"code":"calendar_empty","text":"Önümüzdeki 7 gün için kayıtlı takvim olayı yok; bu, olay olmadığı anlamına gelmez."})
    if memory["status"]=="permission_required":warnings.append({"code":"price_rights","text":"Haber-fiyat araştırması için yerel veri izni onaylanmadı."})
    elif memory["status"]=="scope_limit":warnings.append({"code":"memory_scope","text":"Haber hafızası kapsam sınırı aşıldı."})
    eligible=sum(g.get("statistics") is not None for g in memory["groups"])
    if not eligible:warnings.append({"code":"insufficient_evidence","text":"Yeterli ölçüm grubu yok; haber etkisi tahmini yapılmaz."})
    return {"version":VERSION,"as_of":now.isoformat(),"feeds":feeds,"latest":records[:5],"upcoming":upcoming[:5],"visible_news_count":len(records),"high_priority_count":sum(x["review_priority"]=="high" for x in records),"upcoming_count":len(upcoming),
            "memory_status":memory["status"],"descriptive_groups":eligible,"local_model_configured":model_configured,"model_runtime_verified":False,
            "warnings":warnings,"live_feed_verified":False,"notifications_sent":False,"real_orders":False,
            "limits":"Son 7 günün sınırlı görünür kayıtları; takvim manuel ve doğrulanmamış, RSS sorgu başarısı canlılık kanıtı değildir. Öncelik kategori kuralıdır."}

def snapshot():
    now=datetime.now(timezone.utc)
    news,calendar=manual_records(now)
    model=all(os.getenv(k)=="1" for k in ("CYBERBOT_LOCAL_LLM_ENABLED","CYBERBOT_NEWS_LLM_ENABLED")) and bool(os.getenv("CYBERBOT_OLLAMA_MODEL"))
    return assemble(news,calendar,read_rss(),memory_overview(),now=now,model_configured=model)
