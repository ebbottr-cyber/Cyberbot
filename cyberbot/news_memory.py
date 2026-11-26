"""Descriptive event-return memory, strictly separated from strategy promotion."""
import json,os,sqlite3
from collections import defaultdict
from contextlib import closing
from decimal import Decimal as D,InvalidOperation
from statistics import mean,median,stdev
from .news_impact import HORIZONS,VERSION as IMPACT_VERSION,stamp
from .news_graph import rows
from .research_pipeline import research_path

VERSION="news-memory-1"
MIN_EVENTS=20
MAX_REPORTS=1000
BASES=("publication","first_observed")

def summarize(reports,events):
    """Group by asset, source, resolution, anchor and horizon. No synthetic input."""
    by_ref={e["record_key"]:e for e in events if e.get("event_type")=="news"}
    buckets=defaultdict(list)
    ignored=0
    for report in reports:
        e=by_ref.get(report.get("record_key"))
        if (e is None or report.get("mode")!="local_unverified" or report.get("version")!=IMPACT_VERSION
                or report.get("interval_minutes") not in (1,5) or report.get("event_at")!=e["event_at"]
                or report.get("recorded_at")!=e["recorded_at"]):
            ignored+=1
            continue
        topic=e.get("category",e["kind"])
        for basis in BASES:
            for w in report.get(basis,[]):
                if w.get("status")!="measured" or w.get("minutes") not in HORIZONS:continue
                try:
                    start,end=stamp(w["baseline_at"]),stamp(w["endpoint_at"])
                    anchor=stamp(report["event_at"] if basis=="publication" else report["recorded_at"])
                    value=D(str(w["return_pct"]))
                    if not start<anchor<end or not value.is_finite() or value<=-100:raise ValueError()
                except (ValueError,TypeError,KeyError,InvalidOperation):
                    ignored+=1
                    continue
                scope=(report["market"],report["symbol"],report["source"],report["interval_minutes"],basis,w["minutes"])
                buckets[scope].append({"url":e["url"],"event_at":stamp(e["event_at"]),"topic":topic,"start":start,"end":end,"value":value})
    groups=[];duplicates=conflicts=overlaps=0
    for scope,items in sorted(buckets.items()):
        # Same source article, even when reimported or measured more than once.
        by_url=defaultdict(list)
        for item in items:by_url[item["url"]].append(item)
        candidates=[]
        for same in by_url.values():
            signatures={(x["event_at"],x["topic"],x["start"],x["end"],x["value"]) for x in same}
            if len(signatures)!=1:
                conflicts+=len(same)
                continue
            duplicates+=len(same)-1
            candidates.append(same[0])
        # Exclude ambiguous simultaneous articles rather than count them twice.
        by_time=defaultdict(list)
        for item in candidates:by_time[item["event_at"]].append(item)
        unique=[]
        for same in by_time.values():
            if len(same)>1:
                conflicts+=len(same)
            else:unique.append(same[0])
        # Earliest-finishing non-overlapping windows, across topics in this scope.
        # Shared endpoint is conservatively considered overlap.
        selected=[];last=None
        for item in sorted(unique,key=lambda x:(x["end"],x["start"],x["url"])):
            if last is not None and item["start"]<=last:
                overlaps+=1
                continue
            selected.append(item);last=item["end"]
        topics=defaultdict(list)
        for item in selected:topics[item["topic"]].append(item["value"])
        for topic,values in sorted(topics.items()):
            n=len(values)
            stats=None
            if n>=MIN_EVENTS:
                pct=lambda x: str(D(x).quantize(D(".000001")))
                stats={"mean_return_pct":pct(mean(values)),"median_return_pct":pct(median(values)),
                       "event_return_stddev_pct":pct(stdev(values)),"mean_absolute_return_pct":pct(mean(abs(x) for x in values)),
                       "positive_pct":pct(D(sum(x>0 for x in values))*100/n),
                       "negative_pct":pct(D(sum(x<0 for x in values))*100/n),
                       "flat_pct":pct(D(sum(x==0 for x in values))*100/n)}
            groups.append(dict(zip(("market","symbol","price_source","interval_minutes","basis","horizon_minutes"),scope),
                               category=topic,event_count=n,status="descriptive_only" if stats else "insufficient_sample",statistics=stats))
    return {"version":VERSION,"mode":"local_unverified","minimum_events":MIN_EVENTS,"report_count":len(reports),
            "groups":groups,"excluded":{"duplicate_windows":duplicates,"conflicting_windows":conflicts,"overlapping_windows":overlaps,"invalid_or_hidden":ignored},
            "causal_impact_verified":False,"prediction_verified":False,"promotion_enabled":False,"real_orders":False,
            "limitations":["Yalnız görünür, izin beyanlı yerel ölçümler; sentetik örnekler dahil değil.",
            "Aynı URL ve zaman çakışmaları ayıklanır; farklı yayınların aynı olayı anlatması bütünüyle tespit edilemez.",
            "Her varlık, fiyat kaynağı, çözünürlük, zaman referansı ve ufuk ayrı; gruplar arasında sayılar toplanmaz.",
            "20 örnek deneysel alt sınırdır; bağımsızlık veya istatistiksel anlamlılık kanıtı değildir.",
            "Standart sapma olaylar arası getiri dağılımıdır, gün içi gerçekleşen volatilite değildir.",
            "Gözlenen tepkiler nedensellik, ileri tahmin, işlem getirisi veya otomatik strateji terfisi değildir."]}

def overview(market="ALL"):
    if market not in ("ALL","BIST","NASDAQ","XETRA","FUTURES","SOLANA"):raise ValueError("Geçersiz varlık piyasası.")
    if os.getenv("CYBERBOT_NEWS_PRICE_RIGHTS_CONFIRMED")!="1":
        return {**summarize([],[]),"status":"permission_required","truncated":False}
    events=rows()
    keys=[e["record_key"] for e in events if e.get("event_type")=="news"]
    reports=[];p=research_path()
    if keys and p.is_file():
        with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='news_impact'").fetchone():
                q="SELECT payload FROM news_impact WHERE record_key IN ("+",".join("?" for _ in keys)+") ORDER BY created_at DESC,id DESC LIMIT ?"
                reports=[json.loads(x[0]) for x in db.execute(q,[*keys,MAX_REPORTS+1])]
    truncated=len(reports)>MAX_REPORTS
    # A truncated snapshot could hide conflicting revisions. Fail closed instead of scoring.
    if truncated:return {**summarize([],events),"status":"scope_limit","truncated":True}
    reports=[r for r in reports if market=="ALL" or r.get("market")==market]
    out=summarize(reports,events)
    return {**out,"status":"recorded" if out["groups"] else "empty","truncated":False}
