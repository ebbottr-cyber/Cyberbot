"""Bounded local Futures training observations. No trade or backfill API.

Minute labels are availability cutoffs, not exact exchange tick timestamps.
Collect before the cutoff, store actual source/receipt times, export only closed
cutoffs. Use best-level quantity imbalance consistently and closed 5m taker volume.
"""
import argparse,json,os,sqlite3,time
from contextlib import closing
from datetime import timedelta
from decimal import Decimal as D
import httpx
from . import db_paths,futures_lightgbm as batch
from . import futures_pilot as fut,observed_pilot as stocks
from .providers import binance_observed as b,futures_timeframes as tf,futures_momentum as mom

VERSION="futures-training-1"
KEEP=10080
MAX_CYCLES=240
TABLE="futures_training_minutes_v1"
STEP=timedelta(minutes=1)
def enabled():
    return b.configured() and os.getenv("CYBERBOT_FUTURES_TRAINING_ENABLED")=="1"
def path():
    db_paths.checked();return db_paths.futures_training_path()
def minute(t):return t.replace(second=0,microsecond=0)
def symbol_check(sym):
    if sym not in ("BTCUSDT","ETHUSDT"):raise batch.ResearchError("Eğitim sembolü geçersiz.")

def collect(sym,*,clock=stocks.utc,transport=None):
    if not enabled():raise batch.ResearchError("Eğitim verisi toplama izni kapalı.")
    symbol_check(sym);start=clock()
    if not 40<=start.second<=44:raise batch.ResearchError("Dakika toplama başlangıcı :40–:44 olmalı.")
    end=minute(start)+STEP;cutoff=int(start.timestamp()*1000)-3000
    def check():
        t=clock()
        if not start<=t<end:raise batch.ResearchError("Dakika veri süresi aşıldı.")
        return t
    candle={};atr={}
    with httpx.Client(timeout=httpx.Timeout(4,connect=2),follow_redirects=False,trust_env=False) as client:
        for f in ("1m","5m"):
            check();p=tf.params(sym,f,cutoff,limit=60)
            raw=transport(tf.KLINES,p) if transport is not None else tf.fetch(client,sym,f,cutoff,limit=60)
            rows=tf.parse(raw,f,cutoff,limit=60)
            candle[f]=raw[-1]
            atr[f]=mom.indicators(rows)["atr_pct"]
        raw5=candle["5m"];vol=D(raw5[5]);taker=D(raw5[9])
        if vol<=0:raise batch.ResearchError("Kapalı taker hacmi yok.")
        def get(endpoint):
            check()
            return transport(endpoint,{"symbol":sym}) if transport is not None else b.get(client,endpoint,{"symbol":sym})
        book=get(b.BOOK);mark=get(b.MARK);oi=get(b.OPEN_INTEREST)
        received=check();ctx=b.market_context(book,mark,oi,sym,received)
    stamps=[b.stamp(x["time"]) for x in (book,mark,oi)]
    if any(not end-timedelta(seconds=20)<=t<=received for t in stamps):
        raise batch.ResearchError("Kotasyon kaynak zamanı dakika penceresi dışında.")
    bid,ask=(stocks.dec(book[k]) for k in ("bidPrice","askPrice"))
    if bid>=ask or ctx["best_level_qty_imbalance"] is None:raise batch.ResearchError("Kotasyon veya derinlik geçersiz.")
    mid=(bid+ask)/2
    row={"at":end.isoformat(),"symbol":sym,"source":b.SOURCE,"mid":str(mid),
         "spread_bps":str((ask-bid)/mid*10000),"funding_rate":ctx["reported_last_funding_rate"],
         "mark_index_basis_pct":ctx["mark_index_basis_pct"],"open_interest":ctx["open_interest_base"],
         "book_imbalance":ctx["best_level_qty_imbalance"],"taker_imbalance":str(2*taker/vol-1),
         "atr_1m_pct":atr["1m"],"atr_5m_pct":atr["5m"]}
    validate_row(row,sym,end)
    return {"version":VERSION,"row":row,"started_at":start.isoformat(),"received_at":received.isoformat(),
            "book_at":stamps[0].isoformat(),"mark_at":stamps[1].isoformat(),"open_interest_at":stamps[2].isoformat(),
            "candle_1m_end":b.stamp(candle["1m"][6]+1).isoformat(),"candle_5m_end":b.stamp(raw5[6]+1).isoformat(),
            "transport_mocked":transport is not None,"book_imbalance_method":"best_level_quantity",
            "taker_imbalance_method":"closed_5m_base_volume","real_orders":False}

def validate_row(row,sym,at):
    # Shared batch validator requires >=240 records. Validate one observation
    # against the exact same limits without inventing history.
    if not isinstance(row,dict) or set(row)!=batch.FIELDS or row["symbol"]!=sym or row["source"]!=b.SOURCE or batch.timestamp(row["at"])!=at:
        raise batch.ResearchError("Eğitim satırı kimliği geçersiz.")
    limits={"mid":(1e-8,1e9),"spread_bps":(0,20000),"funding_rate":(-.1,.1),
            "mark_index_basis_pct":(-100,100),"open_interest":(1e-12,1e12),"book_imbalance":(-1,1),
            "taker_imbalance":(-1,1),"atr_1m_pct":(0,100),"atr_5m_pct":(0,100)}
    for k,(lo,hi) in limits.items():batch.numeric(row[k],lo,hi)

def validate_record(record,now,*,allow_mock=False):
    if record.get("version")!=VERSION or record.get("real_orders") is not False or record.get("transport_mocked") is not False and not allow_mock:
        raise batch.ResearchError("Gözlem kaynağı veya güvenlik alanı geçersiz.")
    row=record["row"];sym=row["symbol"];symbol_check(sym);at=batch.timestamp(row["at"])
    validate_row(row,sym,at)
    start=stocks.ts(record["started_at"]);received=stocks.ts(record["received_at"])
    if not at-STEP+timedelta(seconds=40)<=start<at-STEP+timedelta(seconds=45) or not start<=received<at<=now:
        raise batch.ResearchError("Gözlem kullanılabilirlik zamanı geçersiz.")
    ts=[stocks.ts(record[k]) for k in ("book_at","mark_at","open_interest_at")]
    if any(not at-timedelta(seconds=20)<=t<=received for t in ts) or (max(ts)-min(ts)).total_seconds()>3:
        raise batch.ResearchError("Gözlem kaynak zamanı geçersiz.")
    for f in ("1m","5m"):
        step=tf.FRAMES[f];cutoff=int(start.timestamp()*1000)-3000
        if stocks.ts(record["candle_"+f+"_end"])!=b.stamp(cutoff//step*step):
            raise batch.ResearchError("Mum kapanış zamanı geçersiz.")
    if record.get("book_imbalance_method")!="best_level_quantity" or record.get("taker_imbalance_method")!="closed_5m_base_volume":
        raise batch.ResearchError("Eğitim özellik yöntemi değişti.")
    return sym,at

def schema(db,create=False):
    names={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    if names and names!={TABLE}:raise batch.ResearchError("Eğitim veritabanı şeması uyuşmuyor.")
    if not names and create:
        db.execute("CREATE TABLE "+TABLE+"(symbol TEXT NOT NULL,at TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(symbol,at))")
    return bool(names) or create

def save(record,*,clock=stocks.utc):
    if not enabled():raise batch.ResearchError("Eğitim verisi toplama izni kapalı.")
    sym,at=validate_record(record,clock());p=path();p.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(p,timeout=5,isolation_level=None)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            schema(db,True)
            latest=db.execute("SELECT MAX(at) FROM "+TABLE+" WHERE symbol=?",(sym,)).fetchone()[0]
            if latest is not None and at.isoformat()<=latest:
                db.rollback();return {"status":"duplicate_or_old","symbol":sym,"at":at.isoformat()}
            db.execute("INSERT INTO "+TABLE+" VALUES(?,?,?)",(sym,at.isoformat(),json.dumps(record,allow_nan=False,separators=(",",":"))))
            db.execute("DELETE FROM "+TABLE+" WHERE symbol=? AND at NOT IN (SELECT at FROM "+TABLE+" WHERE symbol=? ORDER BY at DESC LIMIT ?)",(sym,sym,KEEP))
            db.commit()
        except BaseException:db.rollback();raise
    return {"status":"recorded","symbol":sym,"at":at.isoformat(),"real_orders":False}

def recent(sym,*,clock=stocks.utc):
    symbol_check(sym);now=clock();p=path()
    if not p.is_file():return []
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not schema(db):return []
        payloads=db.execute("SELECT at,payload FROM "+TABLE+" WHERE symbol=? ORDER BY at DESC LIMIT ?",(sym,batch.MAX_ROWS)).fetchall()
    out=[];later=None
    for at,payload in payloads:
        record=json.loads(payload);actual_sym,t=validate_record(record,now)
        if actual_sym!=sym or t.isoformat()!=at:raise batch.ResearchError("Eğitim depolama kimliği uyuşmuyor.")
        if later is not None and later-t!=STEP:break
        out.append(record["row"]);later=t
    return list(reversed(out))

def export(sym,*,clock=stocks.utc):
    rows=recent(sym,clock=clock)
    batch.validate(rows,sym,clock())
    return rows

def status(sym,*,clock=stocks.utc):
    rows=recent(sym,clock=clock)
    return {"version":VERSION,"symbol":sym,"enabled":enabled(),"contiguous_rows":len(rows),
            "first_at":rows[0]["at"] if rows else None,"last_at":rows[-1]["at"] if rows else None,
            "minimum_training_rows":batch.MIN_ROWS,"training_export_ready":len(rows)>=batch.MIN_ROWS,
            "feature_provenance_independently_verified":False,"real_orders":False}

def run(sym,cycles,*,clock=stocks.utc,sleep=time.sleep):
    if not enabled() or type(cycles) is not int or not 1<=cycles<=MAX_CYCLES:
        raise batch.ResearchError("Toplama izni veya döngü sınırı.")
    symbol_check(sym);results=[]
    for _ in range(cycles):
        now=clock();start=minute(now)+timedelta(seconds=40)
        if now>=start:start+=STEP
        sleep(max(0,(start-now).total_seconds()))
        try:
            record=collect(sym,clock=clock)
            end=batch.timestamp(record["row"]["at"])
            sleep(max(0,(end-clock()).total_seconds()))
            results.append(save(record,clock=clock))
        except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as e:
            results.append({"status":"missed","type":type(e).__name__})
            # no backfill or immediate retry
    return {"version":VERSION,"cycles":cycles,"results":results,"real_orders":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"))
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--cycles",type=int);mode.add_argument("--status",action="store_true");mode.add_argument("--export",action="store_true")
    a=p.parse_args()
    try:
        d=run(a.symbol,a.cycles) if a.cycles is not None else export(a.symbol) if a.export else status(a.symbol)
        print(json.dumps(d,ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as exc:
        # Errors go to stderr so export redirection cannot produce a bogus JSON dataset.
        import sys
        print(json.dumps({"status":"rejected","type":type(exc).__name__}),file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
