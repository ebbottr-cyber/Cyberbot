"""Source-labelled ETF universe; offline scanner, no orders."""
import csv
import sqlite3
from contextlib import closing
from tools.fund_etf_analysis import analyze

def import_catalog(database, filename):
    rows=[]
    with open(filename,encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            values=tuple(r[k].strip() for k in ("isin","symbol","exchange","region","currency","sector","name","source"))
            if not all(values) or values[3] not in ("US","EU","OTHER") or values[4] not in ("USD","EUR","GBP","TRY"):
                raise ValueError("Invalid ETF metadata")
            rows.append(values)
    if not rows or len({(r[1],r[2],r[4]) for r in rows})!=len(rows):
        raise ValueError("Empty or duplicate catalog")
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS etf_catalog (isin TEXT,symbol TEXT,exchange TEXT,region TEXT,currency TEXT,sector TEXT,name TEXT,source TEXT,PRIMARY KEY(symbol,exchange,currency))")
        db.executemany("INSERT INTO etf_catalog VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(symbol,exchange,currency) DO UPDATE SET isin=excluded.isin,region=excluded.region,sector=excluded.sector,name=excluded.name,source=excluded.source",rows)
    return len(rows)

def scan(database, *, region=None, sector=None, price_source="Yahoo Finance", max_age_days=7):
    if max_age_days<0:
        raise ValueError("Invalid age limit")
    with closing(sqlite3.connect(database)) as db, db:
        rows=db.execute("SELECT isin,symbol,exchange,region,currency,sector,name,source FROM etf_catalog WHERE (? IS NULL OR region=?) AND (? IS NULL OR sector=?) ORDER BY symbol,exchange",(region,region,sector,sector)).fetchall()
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fund_prices'").fetchone()
        ambiguous=set(db.execute("SELECT symbol,currency FROM etf_catalog GROUP BY symbol,currency HAVING COUNT(*)>1").fetchall())
    results=[]
    for isin,symbol,exchange,region,currency,sector,name,source in rows:
        if (symbol,currency) in ambiguous:
            metrics={"status":"ambiguous_price_identity"}
        elif exists:
            metrics=analyze(database,"ETF",symbol.upper(),currency,price_source)
        else:
            metrics={"status":"insufficient_data"}
        eligible=metrics.get("status")=="research_only" and 0<=metrics["age_days"]<=max_age_days
        results.append(dict(isin=isin,symbol=symbol,exchange=exchange,region=region,currency=currency,sector=sector,name=name,metadata_source=source,metrics=metrics,research_eligible=eligible,real_orders=False))
    return results
