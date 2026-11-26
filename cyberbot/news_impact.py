"""Offline event-window return measurements, not causal impact or a trading signal."""
import hashlib,json,os,sqlite3
from contextlib import closing
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D,InvalidOperation
from pathlib import Path
from .news_graph import rows,links_for,PATTERNS
from .research_pipeline import research_path

VERSION="event-window-1"
HORIZONS=(5,15,60,1440)
MAX_BYTES=2_000_000

def stamp(value):
    if not isinstance(value,str):raise ValueError("Zaman damgası metin olmalı.")
    t=datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("Saat dilimi gerekli.")
    return t.astimezone(timezone.utc)

def measure(event_at,recorded_at,prices,interval,*,now):
    if type(interval) is not int or interval not in (1,5):raise ValueError("1 veya 5 dakikalık kapanışlar gerekli.")
    if not isinstance(prices,list) or not 2<=len(prices)<=3000:raise ValueError("2–3000 fiyat gözlemi gerekli.")
    event=stamp(event_at);recorded=stamp(recorded_at)
    if event>recorded or recorded>now:raise ValueError("Olay/kayıt zamanı sırası geçersiz.")
    grid={};last=None;step=timedelta(minutes=interval)
    for row in prices:
        t=stamp(row["closed_at"])
        try:p=D(str(row["close"]))
        except InvalidOperation:raise ValueError("Geçersiz fiyat.") from None
        if not p.is_finite() or not D("1e-12")<=p<=D("1e9") or t>now or t.microsecond or t.second or t.minute%interval or (last is not None and t<=last):
            raise ValueError("Geçersiz, gelecekte veya sırasız kapanış.")
        grid[t]=p;last=t
    def window(anchor,minutes):
        target=anchor+timedelta(minutes=minutes)
        # Strictly pre-anchor close; endpoint is first grid close at/after horizon.
        base=anchor.replace(second=0,microsecond=0)-timedelta(minutes=anchor.minute%interval)
        if base==anchor:base-=step
        end=target.replace(second=0,microsecond=0)-timedelta(minutes=target.minute%interval)
        if end<target:end+=step
        out={"minutes":minutes,"baseline_at":base.isoformat(),"endpoint_at":end.isoformat(),"return_pct":None}
        if end>now:return {**out,"status":"pending"}
        t=base
        while t<=end:
            if t not in grid:return {**out,"status":"missing_observations"}
            t+=step
        return {**out,"status":"measured","return_pct":str(((grid[end]/grid[base]-1)*100).quantize(D(".000001")))}
    return {"version":VERSION,"interval_minutes":interval,"event_at":event.isoformat(),"recorded_at":recorded.isoformat(),
            "publication":[window(event,h) for h in HORIZONS],"first_observed":[window(recorded,h) for h in HORIZONS],
            "causal_impact_verified":False,"tradable_return_verified":False,"real_orders":False,
            "limitations":["Kapanışlar: olaydan kesin önceki son grid kapanışı ve ufukta veya sonrasında ilk grid kapanışı. Tam ölçüm zamanları gösterilir.",
             "Aradaki tüm kapanışlar zorunlu. Seans kapanışı, hafta sonu ve eksik verilerde ölçüm yok; interpolasyon yok.",
             "İlk kayıt öncesi tepki, botun erişebildiği getiri değildir. İlk kayıt penceresi de gerçekleşebilir işlem getirisi değildir.",
             "Karşılaştırma endeksi, işlem maliyetleri ve diğer olaylar ayrıştırılmadı; nedensellik veya tahmin başarısı kanıtlanmaz."]}

def demo():
    start=datetime(2000,1,1,tzinfo=timezone.utc)
    prices=[{"closed_at":(start+timedelta(minutes=5*i)).isoformat(),"close":str(D(100)+D(i)/100)} for i in range(300)]
    event=start+timedelta(minutes=6);recorded=start+timedelta(minutes=11)
    return {"mode":"synthetic","market":"DEMO","symbol":"DEMO-NEWS",**measure(event.isoformat(),recorded.isoformat(),prices,5,now=start+timedelta(days=2))}

def run_local(path,record_key,market,symbol):
    if os.getenv("CYBERBOT_NEWS_PRICE_RIGHTS_CONFIRMED")!="1":raise ValueError("Fiyat verisi kullanım/saklama hakkı onaylanmadı.")
    # Only explicit local CLI input. No network or browser-supplied file paths.
    with Path(path).open("rb") as stream:raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError("Fiyat dosyası çok büyük.")
    data=json.loads(raw)
    if data.get("market")!=market or data.get("symbol")!=symbol:raise ValueError("Piyasa/sembol uyuşmuyor.")
    if data.get("timestamp_convention")!="bar_close":raise ValueError("Kapanış zaman damgası sözleşmesi gerekli.")
    source=data.get("source")
    if not isinstance(source,str) or not 1<=len(source)<=120:raise ValueError("Veri kaynağı gerekli.")
    event=next((x for x in rows() if x["record_key"]==record_key and x["event_type"]=="news"),None)
    if event is None:raise ValueError("Görünür haber kaydı bulunamadı.")
    if not any(x["market"]==market and x["symbol"]==symbol for x in links_for([record_key])):raise ValueError("Operatör varlık eşleşmesi gerekli.")
    result=measure(event["event_at"],event["recorded_at"],data["prices"],data["interval_minutes"],now=datetime.now(timezone.utc))
    result.update(mode="local_unverified",record_key=record_key,market=market,symbol=symbol,source=source,asset_verified=False,license_independently_verified=False,price_verified=False)
    # Do not persist incomplete runs without any measurement, nor raw quotes.
    if not any(x["status"]=="measured" for k in ("publication","first_observed") for x in result[k]):
        return {"new":False,"result":result}
    # Deduplicate by inputs and resulting status (pending becomes measurable later).
    key=hashlib.sha256(json.dumps([record_key,market,symbol,VERSION,hashlib.sha256(raw).hexdigest(),result],sort_keys=True,separators=(",",":")).encode()).hexdigest()
    result["id"]=key
    p=research_path()
    with closing(sqlite3.connect(p,timeout=5)) as db,db:
        db.execute("CREATE TABLE IF NOT EXISTS news_impact(id TEXT PRIMARY KEY,record_key TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL)")
        new=bool(db.execute("INSERT OR IGNORE INTO news_impact VALUES(?,?,?,?)",(key,record_key,datetime.now(timezone.utc).isoformat(),json.dumps(result,ensure_ascii=False))).rowcount)
    return {"new":new,"result":result}

def recent():
    if os.getenv("CYBERBOT_NEWS_PRICE_RIGHTS_CONFIRMED")!="1":return []
    keys=[x["record_key"] for x in rows()]
    if not keys:return []
    p=research_path()
    if not p.is_file():return []
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='news_impact'").fetchone():return []
        q="SELECT payload FROM news_impact WHERE record_key IN ("+",".join("?" for _ in keys)+") ORDER BY created_at DESC LIMIT 30"
        return [json.loads(x[0]) for x in db.execute(q,keys)]
