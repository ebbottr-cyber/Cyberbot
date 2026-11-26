"""Opt-in two-pair quote adapter. No trades, history collection, or automatic subscription."""
import json,os,sqlite3,tempfile
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path
import httpx

PAIRS={"USD/TRY":"usdtry","USDT/USD":"usdtusd"}
INTERVAL=240
MAX_AGE=300
DAILY_BUDGET=720
URL="https://api.twelvedata.com/exchange_rate"

class FXError(ValueError):pass

def paths():
    root=Path("var").resolve()
    quote=root/"fx-provider.json"
    quota=root/"fx-provider-quota.sqlite3"
    from .db_paths import checked,same
    forbidden=set(checked().values())
    for env,default in (("CYBERBOT_DB","var/paper.sqlite3"),("CYBERBOT_LEARNING_DB","var/learning.sqlite3"),("CYBERBOT_WORKER_DB","var/worker.sqlite3"),("CYBERBOT_EBBOT_DB","")):
        value=os.getenv(env,default)
        if value:forbidden.add(Path(value).expanduser().resolve())
    if same(quote,quota):raise FXError("Kur dosyaları çakışıyor.")
    for p in (quote,quota):
        if p.is_symlink() or any(p.resolve()==q or (p.exists() and q.exists() and p.samefile(q)) for q in forbidden):
            raise FXError("Kur dosyası yolu çakışıyor.")
    return quote,quota

def reserve(path,now):
    path.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(path,timeout=3,isolation_level=None)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS quota(id INTEGER PRIMARY KEY CHECK(id=1),day TEXT NOT NULL,used INTEGER NOT NULL,last REAL NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT day,used,last FROM quota WHERE id=1").fetchone()
        day=now.date().isoformat();ts=now.timestamp()
        if row and ts-row[2]<INTERVAL:raise FXError("Kur sorgusu için 240 saniye bekleme sınırı.")
        used=row[1] if row and row[0]==day else 0
        if used+2>DAILY_BUDGET:raise FXError("Yerel günlük kur kotası doldu.")
        db.execute("INSERT OR REPLACE INTO quota VALUES(1,?,?,?)",(day,used+2,ts))
        db.commit()

def parse(data,pair,now):
    try:
        if not isinstance(data,dict) or data.get("symbol")!=pair or data.get("status")=="error":raise ValueError()
        rate=D(str(data["rate"]));stamp=data["timestamp"]
        if type(stamp) is not int:raise ValueError()
        observed=datetime.fromtimestamp(stamp,timezone.utc)
        hi=D("1000000") if pair=="USD/TRY" else D("100")
        if not rate.is_finite() or not D(".01")<=rate<=hi:raise ValueError()
        age=(now-observed).total_seconds()
        if not -5<=age<=MAX_AGE:raise FXError("Kur zaman damgası eski veya gelecekte.")
        return str(rate),observed.isoformat()
    except FXError:raise
    except (ValueError,TypeError,KeyError,ArithmeticError,OSError):raise FXError("Kur sağlayıcı yanıtı geçersiz.") from None

def fetch_pair(client,pair,key):
    try:
        with client.stream("GET",URL,params={"symbol":pair,"apikey":key,"dp":8}) as response:
            response.raise_for_status()
            raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>16384:raise FXError("Kur yanıtı çok büyük.")
        return json.loads(raw)
    except (httpx.HTTPError,ValueError,OSError):raise FXError("Kur sağlayıcısı erişim/yanıt hatası.") from None

def refresh(*,transport=None,clock=None):
    if os.getenv("CYBERBOT_FX_PROVIDER_ENABLED")!="1" or os.getenv("CYBERBOT_FX_RIGHTS_CONFIRMED")!="1":
        raise FXError("Kur sağlayıcısı veya kullanım/gösterim izni etkin değil.")
    key=os.getenv("CYBERBOT_TWELVEDATA_KEY","").strip()
    if not key or len(key)>256:raise FXError("Yerel kur API anahtarı eksik.")
    clock=clock or (lambda:datetime.now(timezone.utc))
    quote,quota=paths()
    reserve(quota,clock())
    values={}
    with httpx.Client(timeout=httpx.Timeout(10,connect=4),follow_redirects=False,trust_env=False) as client:
        for pair,name in PAIRS.items():
            raw=transport(pair) if transport else fetch_pair(client,pair,key)
            rate,stamp=parse(raw,pair,clock())
            values[name]=rate
            values[name+"_observed_at"]=stamp
    # Re-check both timestamps at publication; never refresh old data by stamping retrieval time.
    now=clock()
    for name in PAIRS.values():
        age=(now-datetime.fromisoformat(values[name+"_observed_at"])).total_seconds()
        if not -5<=age<=MAX_AGE:raise FXError("Kur çifti yayın sırasında eskidi.")
    values.update(source="Twelve Data exchange_rate",observed_at=min(values["usdtry_observed_at"],values["usdtusd_observed_at"]))
    quote.parent.mkdir(parents=True,exist_ok=True)
    # Replace only the adapter-owned cache, after both quotes pass; no partial publication.
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=quote.parent,prefix=".fx-",suffix=".tmp",delete=False) as stream:
            tmp=Path(stream.name);json.dump(values,stream,allow_nan=False)
            stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,quote)
    finally:
        if tmp and tmp.exists():tmp.unlink()
    return {"status":"updated","observed_at":values["observed_at"],"source":values["source"],"real_orders":False}
