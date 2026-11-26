"""EBBot'un gruplu Yahoo indirme yaklaşımının bağımsız araştırma uyarlaması."""
import argparse
import csv
import hashlib
import json
import math
import sqlite3
import time
from contextlib import closing
from datetime import date,timedelta
from pathlib import Path

from vendor.ebbot.four_market_universe_builder import canonical_equity

MARKETS=("tr","us","de")
BATCH=10

def universe(path,shards,index,pilot):
    if not 1<=shards<=64 or not 0<=index<shards: raise ValueError("Geçersiz parça.")
    result={m:set() for m in MARKETS}
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            m=row["market"]
            if m not in result:raise ValueError("Geçersiz piyasa.")
            result[m].add(canonical_equity(m,row["symbol"]))
    if not all(result.values()):raise ValueError("Üç piyasa listesi gerekli.")
    if sum(map(len,result.values()))>30000:raise ValueError("Envanter sınırı.")
    return {m:[s for i,s in enumerate(sorted(v)[:5] if pilot else sorted(v)) if i%shards==index] for m,v in result.items()}

def normalize(raw,start,end):
    result={}
    bad=set()
    for row in raw:
        try:
            session=date.fromisoformat(str(row[0])[:10])
            o,h,l,c,v=map(float,row[1:6])
            if not start<=session<end or not all(map(math.isfinite,(o,h,l,c,v))) or min(o,h,l,c)<=0 or v<0 or h<max(o,l,c) or l>min(o,h,c):continue
            d=str(session)
            if d in result:
                bad.add(d)
                continue
            result[d]=(d,o,h,l,c,v)
        except (ValueError,TypeError,IndexError,OverflowError):
            continue
    return [result[k] for k in sorted(result) if k not in bad]

def yahoo(symbols,start,end):
    raise RuntimeError("Toplu fiyat indirme kullanıcı kararıyla kapatıldı.")


def collect(path,out,start,end,*,shards=1,index=0,pilot=True,download=None,spacing=2):
    if not start<end<=date.today() or (end-start).days>7300:raise ValueError("Geçersiz tarih aralığı.")
    groups=universe(path,shards,index,pilot)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    fingerprint=hashlib.sha256(json.dumps(groups,sort_keys=True).encode()).hexdigest()
    meta={"schema":1,"start":str(start),"end_exclusive":str(end),"shards":shards,"index":index,"pilot":pilot,"inventory_sha256":fingerprint}
    report={**meta,"mode":"historical_adjusted_unverified","license_verified":False,"venue_verified":False,"real_orders":False,"by_market":{}}
    with closing(sqlite3.connect(out/"daily.sqlite3")) as db:
        db.execute("CREATE TABLE IF NOT EXISTS run_meta(value TEXT NOT NULL)")
        prior=db.execute("SELECT value FROM run_meta").fetchone()
        if prior and json.loads(prior[0])!=meta:raise ValueError("Devam dosyası tarih veya envanter ile uyuşmuyor.")
        if not prior:db.execute("INSERT INTO run_meta VALUES (?)",(json.dumps(meta),))
        db.execute("CREATE TABLE IF NOT EXISTS stock_daily(code TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,data_source TEXT,PRIMARY KEY(code,date))")
        db.execute("CREATE TABLE IF NOT EXISTS attempts(code TEXT PRIMARY KEY, status TEXT NOT NULL)")
        db.commit()
        def save_report():
            for m,symbols in groups.items():
                counts={"candidates":len(symbols),"with_any_bars":0,"rows_in_range":0,"downloaded":0,"no_data":0,"errors":0,"pending":0}
                for s in symbols:
                    n=db.execute("SELECT count(*) FROM stock_daily WHERE code=?",(s,)).fetchone()[0]
                    counts["rows_in_range"]+=n
                    counts["with_any_bars"]+=bool(n)
                    row=db.execute("SELECT status FROM attempts WHERE code=?",(s,)).fetchone()
                    counts[row[0] if row else "pending"]+=1
                report["by_market"][m]=counts
            tmp=out/"coverage.tmp"
            tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            tmp.replace(out/"coverage.json")
        save_report()
        if download is not None:
            for m,symbols in groups.items():
                # A populated series is reused. No claim of complete exchange-session history.
                pending=[s for s in symbols if not db.execute("SELECT 1 FROM stock_daily WHERE code=? LIMIT 1",(s,)).fetchone()]
                empty=0
                for i in range(0,len(pending),BATCH):
                    batch=pending[i:i+BATCH]
                    try:
                        data=download(batch,start,end)
                        if not isinstance(data,dict):raise ValueError("Yanıt biçimi.")
                        error=False
                    except Exception:
                        data={};error=True
                    success=0
                    with db:
                        for s in batch:
                            rows=normalize(data.get(s,[]),start,end)
                            if rows:
                                db.executemany("INSERT OR IGNORE INTO stock_daily VALUES(?,?,?,?,?,?,?,?)",((s,*row,"yahoo_adjusted") for row in rows))
                                success+=1
                            state="downloaded" if rows else "errors" if error else "no_data"
                            db.execute("INSERT OR REPLACE INTO attempts VALUES (?,?)",(s,state))
                    save_report()
                    empty=0 if success else empty+1
                    if empty>=3:break
                    time.sleep(spacing)
        save_report()
    print(json.dumps(report,ensure_ascii=False))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--shards",type=int,default=1)
    p.add_argument("--index",type=int,default=0)
    p.add_argument("--full",action="store_true")
    p.add_argument("--allow-network",action="store_true")
    a=p.parse_args()
    if a.allow_network:p.error("Toplu fiyat indirme kapalı.")
    collect(a.universe,a.output,date.fromisoformat(a.start),date.fromisoformat(a.end),shards=a.shards,index=a.index,pilot=not a.full,download=yahoo if a.allow_network else None)
