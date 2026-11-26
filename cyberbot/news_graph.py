"""Evidence-labelled news relationships, not causal impact or trading advice."""
import hashlib,json,re,sqlite3
from contextlib import closing
from datetime import datetime,timezone
from .news import MARKETS,list_refs,normalize_url
from .news_feed import read as read_rss
from .research_pipeline import research_path

TOPICS={
 "monetary_policy":("trend","momentum","reversion"),
 "inflation":("trend","momentum"),
 "financial_stability":("trend","reversion"),
 "macro":("trend","momentum","reversion"),
 "company":("trend","momentum"),
 "regulation":("trend","momentum"),
 "exchange":("trend","momentum"),
 "ecosystem":("trend","momentum"),
}
NAMES={"trend":"Trend","momentum":"Momentum","reversion":"Ortalamaya dönüş"}
PATTERNS={"BIST":r"[A-Z0-9]{1,12}\.IS","NASDAQ":r"[A-Z][A-Z0-9.-]{0,14}","XETRA":r"[A-Z0-9]{1,12}\.DE","FUTURES":r"[A-Z0-9]{2,20}USDT","SOLANA":r"[1-9A-HJ-NP-Za-km-z]{32,44}"}

def identity(*parts):
    return hashlib.sha256(json.dumps(parts,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def rows(market="ALL",*,news_only=False):
    if market!="ALL" and market not in MARKETS:raise ValueError("Geçersiz piyasa.")
    # Preserve provenance of both record types, with namespaced IDs.
    out=[]
    for origin,items in (("manual",list_refs(market,event_type="news" if news_only else None)["items"]),("rss",read_rss(market)["items"])):
        out.extend({**x,"record_key":origin+":"+x["id"],"origin":origin} for x in items)
    return sorted(out,key=lambda x:(x["event_at"],x["record_key"]),reverse=True)[:100]

def find_record(record_key):
    # Resolve exact records across each supported scope; never bypass RSS permissions.
    if not re.fullmatch(r"(manual|rss):[0-9a-f]{64}",record_key):return None
    origin,key=record_key.split(":",1)
    if origin=="rss":
        # RSS visibility remains controlled by its approved-source and retention filters.
        from .news_feed import read
        for m in sorted(MARKETS):
            for x in read(m)["items"]:
                if x["id"]==key:return {**x,"record_key":record_key,"origin":"rss"}
        return None
    p=research_path()
    if not p.is_file():return None
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='news_refs'").fetchone():return None
        row=db.execute("SELECT payload FROM news_refs WHERE id=?",(key,)).fetchone()
    return {**json.loads(row[0]),"record_key":record_key,"origin":"manual"} if row else None

def asset_link(record_key,market,symbol,evidence_url):
    if market not in PATTERNS or not re.fullmatch(PATTERNS[market],symbol):raise ValueError("Sembol biçimi geçersiz.")
    if market=="NASDAQ" and symbol.endswith((".IS",".DE",".HK",".SS",".SZ")):raise ValueError("NASDAQ sembol biçimi geçersiz.")
    if not re.fullmatch(r"(manual|rss):[0-9a-f]{64}",record_key):raise ValueError("Haber kimliği geçersiz.")
    # A mapping is an operator assertion, not proof of issuer identity, listing, or exposure.
    # Only visible current records are linkable; disabled feeds cannot be used.
    if find_record(record_key) is None:raise ValueError("Haber bulunamadı veya görünür değil.")
    url=normalize_url(evidence_url)
    data={"record_key":record_key,"market":market,"symbol":symbol,"evidence_url":url,
          "status":"operator_asserted","verified":False,"created_at":datetime.now(timezone.utc).isoformat()}
    key=identity(record_key,market,symbol,url)
    p=research_path()
    with closing(sqlite3.connect(p,timeout=5)) as db,db:
        db.execute("CREATE TABLE IF NOT EXISTS news_asset_links(id TEXT PRIMARY KEY,record_key TEXT NOT NULL,payload TEXT NOT NULL)")
        new=bool(db.execute("INSERT OR IGNORE INTO news_asset_links VALUES(?,?,?)",(key,record_key,json.dumps(data,ensure_ascii=False))).rowcount)
    return {"new":new,"id":key,"verified":False}

def links_for(keys):
    if not keys:return []
    p=research_path()
    if not p.is_file():return []
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='news_asset_links'").fetchone():return []
        q="SELECT payload FROM news_asset_links WHERE record_key IN ("+",".join("?" for _ in keys)+") ORDER BY rowid DESC LIMIT 200"
        return [json.loads(x[0]) for x in db.execute(q,keys)]

def graph(market="ALL"):
    records=rows(market);links=links_for([x["record_key"] for x in records])
    nodes={};edges={}
    def node(kind,key,label):
        ident=identity(kind,key)[:32]
        nodes.setdefault(ident,{"id":ident,"kind":kind,"label":label})
        return ident
    def edge(a,b,relation,evidence):
        ident=identity(a,b,relation,evidence)[:32]
        edges.setdefault(ident,{"id":ident,"fromNode":a,"toNode":b,"relation":relation,"evidence":evidence})
    for row in records:
        ref=row["record_key"]
        n=node("news",ref,row["label"])
        m=node("market",row["market"],row["market"])
        source=node("source",row["source"],row["source"])
        topic=row.get("category",row["kind"])
        t=node("topic",topic,topic)
        edge(source,n,"source_reference",ref)
        edge(n,m,"recorded_scope",ref)
        edge(n,t,"recorded_category",ref)
        if row.get("event_type")=="news":
            for strategy in TOPICS.get(topic,()):
                s=node("strategy",strategy,NAMES[strategy])
                edge(t,s,"research_hypothesis","topic_rule_v1")
    for link in links:
        n=node("news",link["record_key"],"Haber")
        a=node("asset",link["market"]+":"+link["symbol"],link["market"]+":"+link["symbol"])
        m=node("market",link["market"],link["market"])
        edge(n,a,"operator_asserted",link["evidence_url"])
        edge(a,m,"operator_market_assertion",link["evidence_url"])
    return {"market":market,"records":records,"asset_links":links,"nodes":list(nodes.values()),"edges":list(edges.values()),
            "record_count":len(records),"causal_impact_verified":False,"sentiment":"not_assessed","real_orders":False,
            "limitations":["Piyasa kapsamı kaynaktan veya operatörden gelir; etkilendiği anlamına gelmez.",
            "Strateji bağlantıları araştırma hipotezidir, sinyal veya performans kanıtı değildir.",
            "Varlık eşleşmeleri operatör beyanıdır; borsa ve şirket kimliği doğrulanmaz.",
            "Son 100 görünür kayıt ve 200 eşleşme; kapalı RSS kayıtları kullanılmaz."]}
def canvas_summary():
    """Export structural aggregates only; do not export publisher titles or asset evidence URLs."""
    d=graph()
    from collections import Counter
    counts=Counter(x["market"] for x in d["records"])
    nodes=[{"id":"news-hub","type":"text","text":"Haber araştırma kapsamı\nEtki doğrulanmadı","x":0,"y":0,"width":300,"height":140}]
    edges=[]
    for i,m in enumerate(sorted(MARKETS)):
        ident="scope-"+m
        nodes.append({"id":ident,"type":"text","text":m+" · "+str(counts[m])+" kayıt","x":(i%3)*320-320,"y":200+(i//3)*160,"width":280,"height":120})
        edges.append({"id":"edge-"+m,"fromNode":"news-hub","toNode":ident,"label":"Kayıt kapsamı"})
    return {"nodes":nodes,"edges":edges}
