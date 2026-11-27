"""Offline TEFAS catalog; source-provided categories, no inferred classifications."""
import csv
import re
import sqlite3
from tools.fund_etf_analysis import analyze

def import_catalog(database, filename):
    entries=[]
    with open(filename,encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            code=row["symbol"].strip().upper()
            name=row["name"].strip()
            category=row["category"].strip()
            if not re.fullmatch(r"[A-Z0-9]{3,12}",code) or not name or not category:
                raise ValueError("Invalid fund catalog entry")
            entries.append((code,name,category))
    if not entries:
        raise ValueError("Empty catalog")
    if len({r[0] for r in entries})!=len(entries):
        raise ValueError("Duplicate fund code")
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE IF NOT EXISTS tefas_catalog (symbol TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL)")
        db.executemany("INSERT INTO tefas_catalog VALUES (?,?,?) ON CONFLICT(symbol) DO UPDATE SET name=excluded.name,category=excluded.category",entries)
    return len(entries)

def scan(database, *, category=None, source="TEFAS", max_age_days=7):
    if max_age_days<0:
        raise ValueError("Invalid age limit")
    with sqlite3.connect(database) as db:
        rows=db.execute("SELECT symbol,name,category FROM tefas_catalog WHERE (? IS NULL OR category=?) ORDER BY symbol",(category,category)).fetchall()
        has_prices=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fund_prices'").fetchone()
    results=[]
    for symbol,name,group in rows:
        metrics=analyze(database,"TEFAS",symbol,"TRY",source) if has_prices else {"status":"insufficient_data"}
        eligible=metrics.get("status")=="research_only" and 0<=metrics["age_days"]<=max_age_days
        results.append({"symbol":symbol,"name":name,"category":group,"metrics":metrics,"research_eligible":eligible,"real_orders":False})
    return results
