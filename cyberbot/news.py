"""Manual source-reference and economic calendar journal. No scraping or trading."""
import hashlib,json,sqlite3
from contextlib import closing
from datetime import datetime,timezone
from urllib.parse import urlsplit,urlunsplit
from .research_pipeline import research_path

SOURCES=(
    ("BIST","KAP","https://kap.org.tr/tr/bildirim-sorgu"),
    ("BIST","TCMB","https://www.tcmb.gov.tr/wps/wcm/connect/tr/tcmb%2Btr/main%2Bmenu/duyurular/basin"),
    ("NASDAQ","SEC","https://www.sec.gov/about/rss-feeds"),
    ("NASDAQ","FED","https://www.federalreserve.gov/feeds/feeds.htm"),
    ("XETRA","ECB","https://www.ecb.europa.eu/home/html/rss.en.html"),
    ("FUTURES","Binance","https://www.binance.com/en/support/announcement"),
    ("SOLANA","Solana","https://solana.com/news"),
    ("GLOBAL","GDELT","https://www.gdeltproject.org/"),
)
MARKETS={x[0] for x in SOURCES}
KINDS=("company","macro","regulation","exchange","ecosystem","other")
def normalize_url(value):
    if not isinstance(value,str) or len(value)>2048 or any(ord(c)<33 or c=="\\" for c in value):raise ValueError("Geçersiz kaynak bağlantısı.")
    u=urlsplit(value)
    if u.scheme!="https" or not u.hostname or u.username or u.password or u.port not in (None,443):raise ValueError("HTTPS kaynak bağlantısı gerekli.")
    return urlunsplit(("https",u.hostname.lower(),u.path or "/",u.query,""))
def validate(item):
    market=item["market"];kind=item["kind"];event=item["event_type"]
    if market not in MARKETS or kind not in KINDS or event not in ("news","calendar"):raise ValueError("Geçersiz sınıflandırma.")
    url=normalize_url(item["url"])
    stamp=datetime.fromisoformat(item["event_at"].replace("Z","+00:00"))
    if stamp.tzinfo is None:raise ValueError("Saat dilimi gerekli.")
    stamp=stamp.astimezone(timezone.utc)
    now=datetime.now(timezone.utc)
    if event=="news" and stamp>now:raise ValueError("Gelecekteki haber yerine takvim kaydı kullanın.")
    title=item["label"].strip();note=item.get("note","").strip()
    if not 1<=len(title)<=160 or len(note)>500:raise ValueError("Kısa özgün etiket ve not gerekli.")
    key=hashlib.sha256(json.dumps([url,market,event,stamp.isoformat()],separators=(",",":")).encode()).hexdigest()
    return {"id":key,"market":market,"kind":kind,"event_type":event,"url":url,"source":urlsplit(url).hostname,"event_at":stamp.isoformat(),"label":title,"note":note,"recorded_at":now.isoformat(),"source_verified":False,"impact":"not_measured","sentiment":"not_assessed"}
def save(item):
    d=validate(item);path=research_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(path,timeout=5)) as db,db:
        db.execute("CREATE TABLE IF NOT EXISTS news_refs(id TEXT PRIMARY KEY,market TEXT NOT NULL,event_at TEXT NOT NULL,payload TEXT NOT NULL)")
        new=bool(db.execute("INSERT OR IGNORE INTO news_refs VALUES(?,?,?,?)",(d["id"],d["market"],d["event_at"],json.dumps(d,ensure_ascii=False))).rowcount)
    return {"new":new,"id":d["id"]}
def list_refs(market="ALL"):
    if market!="ALL" and market not in MARKETS:raise ValueError("Geçersiz piyasa.")
    result={"items":[],"sources":[{"market":m,"name":n,"url":u} for m,n,u in SOURCES if market in ("ALL",m)],"automatic_feed_enabled":False,"impact_verified":False,"real_orders":False}
    p=research_path()
    if not p.is_file():return result
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='news_refs'").fetchone():return result
        if market=="ALL":rows=db.execute("SELECT payload FROM news_refs ORDER BY event_at DESC LIMIT 100")
        else:rows=db.execute("SELECT payload FROM news_refs WHERE market=? ORDER BY event_at DESC LIMIT 100",(market,))
        result["items"]=[json.loads(row[0]) for row in rows]
    return result
