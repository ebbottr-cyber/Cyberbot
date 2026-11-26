"""Bounded opt-in official RSS metadata collection; no article fetches or order authority."""
import hashlib,json,os,sqlite3,time
from contextlib import closing
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import httpx
from .news import normalize_url
from .research_pipeline import research_path

FEEDS={
 "fed": {"name":"Federal Reserve Board","url":"https://www.federalreserve.gov/feeds/press_monetary.xml","host":"www.federalreserve.gov","market":"NASDAQ","rights":"https://www.federalreserve.gov/disclaimer.htm"},
 "ecb": {"name":"European Central Bank","url":"https://www.ecb.europa.eu/rss/press.html","host":"www.ecb.europa.eu","market":"XETRA","rights":"https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html"},
}
INTERVAL=900
MAX_BYTES=1048576
MAX_ITEMS=40
class FeedError(ValueError):pass

def enabled_keys():
    if os.getenv("CYBERBOT_NEWS_ENABLED")!="1":return []
    approved=set(os.getenv("CYBERBOT_NEWS_APPROVED","").split(","))
    return [k for k in FEEDS if k in approved]

def category(title):
    s=title.casefold()
    rules=[("monetary_policy",("monetary policy","interest rate","fomc","policy rate","rate decision")),
           ("inflation",("inflation","consumer price","price stability")),
           ("financial_stability",("financial stability","banking supervision","systemic risk")),
           ("macro",("economic outlook","growth","employment","economic projections"))]
    return next((name for name,terms in rules if any(t in s for t in terms)),"other")

def parse(raw,key,now):
    if not isinstance(raw,bytes) or len(raw)>MAX_BYTES:raise FeedError("RSS boyutu geçersiz.")
    # Restrict input to UTF-8 XML and reject all DTD/entity declarations before parsing.
    try:
        decoded=raw.decode("utf-8-sig")
    except UnicodeError:raise FeedError("RSS kodlaması geçersiz.") from None
    if "\x00" in decoded or "<!doctype" in decoded.casefold() or "<!entity" in decoded.casefold():raise FeedError("RSS XML bildirimi reddedildi.")
    try:root=ET.fromstring(decoded)
    except ET.ParseError:raise FeedError("RSS XML geçersiz.") from None
    if root.tag!="rss" or root.find("channel") is None:raise FeedError("RSS 2.0 akışı gerekli.")
    feed=FEEDS[key];rows={}
    for item in root.find("channel").findall("item")[:MAX_ITEMS]:
        try:
            url=normalize_url(item.findtext("link","").strip())
            if urlsplit(url).hostname!=feed["host"]:continue
            title=" ".join(item.findtext("title","").split())
            if not title or len(title)>300:continue
            stamp=parsedate_to_datetime(item.findtext("pubDate",""))
            if stamp.tzinfo is None:continue
            stamp=stamp.astimezone(timezone.utc)
            if stamp>now or stamp<now-timedelta(days=30):continue
            # One stable source URL = one reference, not multiple observations per update.
            ident=hashlib.sha256(url.encode()).hexdigest()
            rows.setdefault(ident,{"id":ident,"market":feed["market"],"kind":"macro","event_type":"news","url":url,
                "source":feed["name"],"source_id":key,"event_at":stamp.isoformat(),"recorded_at":now.isoformat(),
                "label":title,"note":"","origin":"official_rss","category":category(title),
                "classification":"keyword_only","source_verified":False,"impact":"not_measured","sentiment":"not_assessed",
                "rights_url":feed["rights"],"related_markets":["GLOBAL"],"symbol_matches":[]})
        except (ValueError,TypeError,AttributeError,OverflowError):continue
    return list(rows.values())

def fetch(key):
    try:
        with httpx.Client(timeout=httpx.Timeout(12,connect=4),trust_env=False,follow_redirects=False) as client:
            with client.stream("GET",FEEDS[key]["url"],headers={"User-Agent":"Cyberbot research RSS reader/1.0","Accept":"application/rss+xml, application/xml, text/xml"}) as response:
                response.raise_for_status()
                raw=bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw)>MAX_BYTES:raise FeedError("RSS boyut sınırı.")
                return bytes(raw)
    except httpx.HTTPError:raise FeedError("RSS sağlayıcı erişimi başarısız.") from None

def refresh(key,*,transport=None,clock=None):
    if key not in enabled_keys():raise FeedError("RSS kaynağı veya kullanım izni etkin değil.")
    clock=clock or (lambda:datetime.now(timezone.utc))
    now=clock();path=research_path();path.parent.mkdir(parents=True,exist_ok=True)
    # Reserve before network call, persistent across processes and failures.
    with closing(sqlite3.connect(path,timeout=5,isolation_level=None)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS news_feed_state(source TEXT PRIMARY KEY,last_attempt TEXT NOT NULL,last_success TEXT,status TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        old=db.execute("SELECT last_attempt FROM news_feed_state WHERE source=?",(key,)).fetchone()
        if old and (now-datetime.fromisoformat(old[0])).total_seconds()<INTERVAL:raise FeedError("RSS sorgusu için 15 dakika bekleyin.")
        db.execute("INSERT INTO news_feed_state VALUES(?,?,NULL,'attempted') ON CONFLICT(source) DO UPDATE SET last_attempt=excluded.last_attempt,status='attempted'",(key,now.isoformat()))
        db.commit()
    try:
        rows=parse((transport or fetch)(key),key,clock())
        with closing(sqlite3.connect(path,timeout=5)) as db,db:
            db.execute("CREATE TABLE IF NOT EXISTS news_rss_refs(id TEXT PRIMARY KEY,source TEXT NOT NULL,market TEXT NOT NULL,event_at TEXT NOT NULL,payload TEXT NOT NULL)")
            new=0
            for row in rows:
                new+=db.execute("INSERT OR IGNORE INTO news_rss_refs VALUES(?,?,?,?,?)",(row["id"],key,row["market"],row["event_at"],json.dumps(row,ensure_ascii=False))).rowcount
            db.execute("UPDATE news_feed_state SET last_success=?,status='ok' WHERE source=?",(clock().isoformat(),key))
            db.execute("DELETE FROM news_rss_refs WHERE source=? AND event_at<?",(key,(clock()-timedelta(days=30)).isoformat()))
        return {"source":key,"status":"ok","received":len(rows),"new":new,"real_orders":False}
    except Exception:
        with closing(sqlite3.connect(path,timeout=5)) as db,db:db.execute("UPDATE news_feed_state SET status='failed' WHERE source=?",(key,))
        raise

def read(market="ALL"):
    approved=enabled_keys()
    result={"items":[],"feeds":[{"id":k,"name":v["name"],"market":v["market"],"rights_url":v["rights"],"enabled":k in approved,"status":"not_started","last_success":None} for k,v in FEEDS.items()],"automatic_feed_enabled":bool(approved),"real_orders":False}
    path=research_path()
    if not path.is_file():return result
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "news_feed_state" in tables:
            states={k:(a,b) for k,a,b in db.execute("SELECT source,status,last_success FROM news_feed_state")}
            for f in result["feeds"]:
                if f["id"] in states:f["status"],f["last_success"]=states[f["id"]]
        if "news_rss_refs" in tables and approved:
            query="SELECT payload FROM news_rss_refs WHERE source IN ("+",".join("?" for _ in approved)+") AND event_at>=?"
            args=[*approved,(datetime.now(timezone.utc)-timedelta(days=30)).isoformat()]
            if market!="ALL":query+=" AND market=?";args.append(market)
            result["items"]=[json.loads(row[0]) for row in db.execute(query+" ORDER BY event_at DESC LIMIT 100",args)]
    return result

def analysis(market="ALL"):
    from collections import Counter
    data=read(market)
    rows=data["items"]
    return {"mode":"official_rss_metadata","market":market,"observations":len(rows),
            "categories":dict(Counter(x["category"] for x in rows)),
            "sources":dict(Counter(x["source"] for x in rows)),
            "latest_event_at":max((x["event_at"] for x in rows),default=None),
            "classification":"keyword_only","llm_verified":False,"sentiment":"not_assessed","impact":"not_measured","real_orders":False}
