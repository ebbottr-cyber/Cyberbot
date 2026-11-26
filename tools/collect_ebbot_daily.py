"""EBBot'un mevcut toplu Yahoo motorunu yerel Python ortamında çalıştırır.
Kaynak arşiv ve önbellek salt okunur; çıktı yalnız Cyberbot'a ait ayrı SQLite.
Günlük araştırma; 5 dakikalık veya canlı fiyat değildir.
"""
import argparse,csv,json,os,sqlite3,sys,math
from contextlib import closing
from datetime import date,timedelta
from pathlib import Path

def connect_ro(path):
    return sqlite3.connect(Path(path).resolve(strict=True).as_uri()+"?mode=ro",uri=True,timeout=5)

def checked(rows,start,end):
    valid={}
    for row in rows:
        try:
            d=date.fromisoformat(str(row[0])[:10])
            if not start<=d<end: continue
            o,h,l,c,v=map(float,row[1:6])
            if not all(map(math.isfinite,(o,h,l,c,v))) or min(o,h,l,c)<=0 or v<0 or h<max(o,l,c) or l>min(o,h,c): continue
            if d.isoformat() in valid: raise ValueError("duplicate")
            source=str(row[6]).strip()
            if not source or source=="None": continue
            valid[d.isoformat()]=(d.isoformat(),o,h,l,c,v,source)
        except (ValueError,TypeError,OverflowError,IndexError):
            continue
    return list(valid.values())

def read_archive(path,symbol,start,end):
    if not path:return []
    try:
        with closing(connect_ro(path)) as c:
            return checked(c.execute("SELECT date,open,high,low,close,volume,data_source FROM stock_daily WHERE code=? AND date>=? AND date<?",(symbol,str(start),str(end))),start,end)
    except sqlite3.Error: return []

def cached(path,key,start,end):
    if not path or not Path(path).is_file():return []
    try:
        with closing(connect_ro(path)) as c:
            row=c.execute("SELECT payload FROM bars WHERE cache_key=?",(key,)).fetchone()
        if row is None:return []
        payload=json.loads(row[0])
        return checked(((x.get("Date",x.get("Datetime",x.get("index"))),x.get("Open"),x.get("High"),x.get("Low"),x.get("Close"),x.get("Volume"),"yahoo_adjusted") for x in payload),start,end)
    except (sqlite3.Error,ValueError,TypeError,AttributeError):return []

def run(args):
    start,end=map(date.fromisoformat,(args.start,args.end))
    if not start<end<=date.today():raise ValueError("Geçerli geçmiş tarih aralığı gerekli.")
    output=Path(args.output).resolve()
    source=Path(args.archive).resolve(strict=True) if args.archive else None
    old_cache=Path(args.cache).resolve(strict=True) if args.cache else None
    cache=output.with_suffix(".download-cache.sqlite3")
    if output in (source,old_cache) or cache in (source,old_cache):raise ValueError("Kaynak ve çıktı ayrı olmalı.")
    root=Path(args.ebbot_root).resolve(strict=True)
    sys.path.insert(0,str(root))
    # EBBot'un eski paneli veya sunucusu başlatılmaz.
    from scripts.check_four_market_live import MARKETS,load_universe
    import exchange_calendars as xcals
    universe=load_universe(Path(args.universe))
    if not all(universe.values()):raise ValueError("Üç piyasa listesi gerekli.")
    expected={}
    for m in universe:
        cal=xcals.get_calendar(MARKETS[m]["calendar"])
        expected[m]={x.date().isoformat() for x in cal.sessions_in_range(str(start),str(end-timedelta(days=1)))}
    if not all(expected.values()):raise ValueError("Seans bulunamadı.")
    output.parent.mkdir(parents=True,exist_ok=True)
    os.environ.update({"YFINANCE_CACHE_ENABLED":"true","YFINANCE_CACHE_DB":str(cache),"YFINANCE_BATCH_SIZE":"10","YFINANCE_MIN_INTERVAL_SECONDS":"2","YFINANCE_RETRY_MAX":"2"})
    from data_provider.yfinance_fetcher import YfinanceFetcher
    fetcher=YfinanceFetcher() if args.allow_network else None
    report={"start":str(start),"end_exclusive":str(end),"network_allowed":args.allow_network,"real_orders":False,"license_verified":False,"by_market":{}}
    with closing(sqlite3.connect(output,timeout=10)) as db,db:
        db.execute("CREATE TABLE IF NOT EXISTS stock_daily(code TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,data_source TEXT,PRIMARY KEY(code,date))")
        def store(symbol,rows):
            if not rows:return
            # Tek sembol/tarih aralığında fiyat serilerini karıştırma.
            db.execute("DELETE FROM stock_daily WHERE code=? AND date>=? AND date<?",(symbol,str(start),str(end)))
            db.executemany("INSERT INTO stock_daily VALUES(?,?,?,?,?,?,?,?)",((symbol,*v) for v in rows))
            db.commit()
        for m,symbols in universe.items():
            counts={"candidates":len(symbols),"reused":0,"downloaded":0,"with_any_bars":0,"complete_calendar":0,"rows_in_range":0,"missing_or_incomplete":[]}
            report["by_market"][m]=counts
            pending=[]
            complete=lambda rows: expected[m].issubset({x[0] for x in rows})
            for symbol in symbols:
                prev=read_archive(output,symbol,start,end)
                orig=read_archive(source,symbol,start,end)
                key=f"{symbol}|{start}|{end}|adjusted"
                choices=[prev,orig,cached(old_cache,key,start,end),cached(cache,key,start,end)]
                best=max(choices,key=lambda rows:len(expected[m].intersection(x[0] for x in rows)))
                if best!=prev:store(symbol,best)
                if complete(best):counts["reused"]+=1
                else:pending.append(symbol)
            if fetcher:
                empty_batches=0
                for i in range(0,len(pending),10):
                    chunk=pending[i:i+10]
                    try:
                        fetcher.prefetch_daily_batch(chunk,start_date=str(start),end_date=str(end))
                    except Exception:
                        pass
                    successful=0
                    for symbol in chunk:
                        key=f"{fetcher._convert_stock_code(symbol)}|{start}|{end}|adjusted"
                        rows=cached(cache,key,start,end)
                        prev=read_archive(output,symbol,start,end)
                        if rows:successful+=1
                        if len(expected[m].intersection(x[0] for x in rows))>len(expected[m].intersection(x[0] for x in prev)):
                            store(symbol,rows)
                            counts["downloaded"]+=1
                    empty_batches=0 if successful else empty_batches+1
                    if empty_batches>=3:
                        counts["provider_circuit_breaker"]=True
                        break
            for symbol in symbols:
                rows=read_archive(output,symbol,start,end)
                counts["rows_in_range"]+=len(rows)
                counts["with_any_bars"]+=bool(rows)
                counts["complete_calendar"]+=complete(rows)
                if not complete(rows):counts["missing_or_incomplete"].append(symbol)
    report_path=output.with_suffix(".coverage.json")
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ebbot-root",required=True)
    p.add_argument("--universe",required=True)
    p.add_argument("--archive")
    p.add_argument("--cache")
    p.add_argument("--output",required=True)
    p.add_argument("--start",default=str(date.today()-timedelta(days=365)))
    p.add_argument("--end",default=str(date.today()))
    p.add_argument("--allow-network",action="store_true",help="Sağlayıcı erişim, araştırma ve saklama hakkı kontrol edildiyse aç.")
    run(p.parse_args())
