"""Import an existing EBBot equity 5m database without network or source writes.
Derived bars are UTC-aligned, complete 15/30 minute windows, NOT venue-verified.
No trading, provider requests or automatic publication.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import os

FIELDS = "market,ticker,ts_utc,open,high,low,close,volume,fetched_at_utc"
MARKETS = {"BIST","TR","NASDAQ","NYSE","US","XETRA","DE"}
REVIEW = {"US_UNMATCHED"}

def utc(value):
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timezone required")
    return d.astimezone(timezone.utc)

def valid(row, cutoff):
    market, ticker, stamp, o,h,l,c,v,fetched = row
    market = str(market).upper().strip()
    ticker = str(ticker).upper().strip()
    if market not in MARKETS or not ticker or ticker == "XU100.IS":
        raise ValueError("unclassified market or symbol")
    if market in {"BIST","TR"} and not ticker.endswith(".IS"):
        raise ValueError("BIST suffix")
    if market in {"XETRA","DE"} and not ticker.endswith(".DE"):
        raise ValueError("Xetra suffix")
    t = utc(stamp)
    if t.second or t.microsecond or t.minute % 5 or t + timedelta(minutes=5) > cutoff:
        raise ValueError("unaligned or unfinished bar")
    f = utc(fetched)
    if f < t or f > cutoff:
        raise ValueError("invalid fetched timestamp")
    o,h,l,c,v = map(float,(o,h,l,c,v))
    if not all(map(math.isfinite,(o,h,l,c,v))) or min(o,h,l,c)<=0 or v<0 or h<max(o,l,c) or l>min(o,h,c):
        raise ValueError("invalid OHLCV")
    return market,ticker,t.isoformat(),o,h,l,c,v,f.isoformat()

def derive(db, interval):
    table=f"candles_{interval}m"
    db.execute(f"CREATE TABLE {table}(market TEXT,ticker TEXT,ts_utc TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(market,ticker,ts_utc))")
    db.execute(f"""
      INSERT INTO {table}
      WITH b AS (
        SELECT *, CAST(strftime('%s',ts_utc) AS INTEGER) AS epoch
        FROM candles_5m
      ), w AS (
        SELECT *, epoch - epoch % ({interval}*60) AS bucket FROM b
      ), g AS (
        SELECT market,ticker,bucket,max(high) AS h,min(low) AS l,sum(volume) AS v
        FROM w GROUP BY market,ticker,bucket
        HAVING count(*)={interval//5}
          AND min(epoch)=bucket AND max(epoch)=bucket+({interval}-5)*60
      )
      SELECT g.market,g.ticker,strftime('%Y-%m-%dT%H:%M:%S',g.bucket,'unixepoch')||'+00:00',
        first.open,g.h,g.l,last.close,g.v
      FROM g
      JOIN candles_5m first ON first.market=g.market AND first.ticker=g.ticker
        AND first.ts_utc=strftime('%Y-%m-%dT%H:%M:%S',g.bucket,'unixepoch')||'+00:00'
      JOIN candles_5m last ON last.market=g.market AND last.ticker=g.ticker
        AND last.ts_utc=strftime('%Y-%m-%dT%H:%M:%S',g.bucket+({interval}-5)*60,'unixepoch')||'+00:00'
    """)
    return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

def run(source, output):
    source=Path(source).resolve(strict=True)
    output=Path(output).resolve()
    if source==output or output.exists():
        raise ValueError("Output must be new and separate from source")
    output.parent.mkdir(parents=True,exist_ok=True)
    cutoff=datetime.now(timezone.utc)
    report={"source":source.name,"interval":"5m","source_read_only":True,
            "network_requests":0,"real_orders":False,"venue_verified":False,
            "license_verified":False,"derived_alignment":"UTC fixed windows; no session verification",
            "excluded":{}}
    fd,tmp=tempfile.mkstemp(dir=output.parent,suffix=".sqlite3")
    os.close(fd)
    src=db=None
    try:
        src=sqlite3.connect(source.as_uri()+"?mode=ro",uri=True,timeout=20)
        src.execute("PRAGMA query_only=ON")
        src.execute("BEGIN")
        if src.execute("PRAGMA quick_check").fetchone()!=("ok",):
            raise ValueError("Source database integrity failure")
        cols={r[1] for r in src.execute("PRAGMA table_info(candles_5m)")}
        if not set(FIELDS.split(",")).issubset(cols):
            raise ValueError("Unexpected source schema")
        db=sqlite3.connect(tmp)
        db.execute("CREATE TABLE candles_5m(market TEXT,ticker TEXT,ts_utc TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,fetched_at_utc TEXT,PRIMARY KEY(market,ticker,ts_utc))")
        reasons=Counter()
        batch=[]
        total=0
        for row in src.execute("SELECT "+FIELDS+" FROM candles_5m"):
            total+=1
            try:
                batch.append(valid(row,cutoff))
            except (ValueError,TypeError,OverflowError) as exc:
                reasons[str(exc) if isinstance(exc,ValueError) else "bad value"]+=1
            if len(batch)>=5000:
                db.executemany("INSERT INTO candles_5m VALUES (?,?,?,?,?,?,?,?,?)",batch)
                batch.clear()
        if batch:
            db.executemany("INSERT INTO candles_5m VALUES (?,?,?,?,?,?,?,?,?)",batch)
        db.commit()
        n=db.execute("SELECT count(*) FROM candles_5m").fetchone()[0]
        if not n or total!=n+sum(reasons.values()):
            raise ValueError("Empty or inconsistent import")
        report.update(source_rows=total,imported_rows=n,excluded=dict(reasons),
            by_market=[{"market":m,"symbols":s,"rows":r,"start":a,"end":b}
                for m,s,r,a,b in db.execute("SELECT market,count(distinct ticker),count(*),min(ts_utc),max(ts_utc) FROM candles_5m GROUP BY market")],
            derived={str(i):derive(db,i) for i in (15,30)})
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()!=("ok",):
            raise ValueError("Output integrity failure")
        report["integrity_check"]="ok"
        db.execute("CREATE TABLE import_manifest(value TEXT NOT NULL)")
        db.execute("INSERT INTO import_manifest VALUES (?)",(json.dumps(report,ensure_ascii=False),))
        db.commit()
        db.close();db=None
        src.close();src=None
        # Atomic no-overwrite publication on same filesystem.
        os.link(tmp,output)
        Path(tmp).unlink()
        return report
    finally:
        if db is not None: db.close()
        if src is not None: src.close()
        Path(tmp).unlink(missing_ok=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    print(json.dumps(run(a.source,a.output),indent=2,ensure_ascii=False))
