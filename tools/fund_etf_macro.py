"""Offline macro observations with release dates; no automatic provider access."""
import csv
import sqlite3
from datetime import date
from decimal import Decimal

def import_macro(database, filename, source):
    if source not in ("TCMB EVDS","FRED"):
        raise ValueError("Unsupported source")
    rows=[]
    with open(filename,encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            period=date.fromisoformat(r["period"])
            released=date.fromisoformat(r["released"])
            value=Decimal(r["value"])
            if not r["series"].strip() or not r["unit"].strip() or not value.is_finite() or not period<=released<=date.today():
                raise ValueError("Invalid macro observation")
            rows.append((source,r["series"],r["unit"],period.isoformat(),released.isoformat(),str(value)))
    if not rows:
        raise ValueError("Empty macro file")
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE IF NOT EXISTS fund_macro (source TEXT,series TEXT,unit TEXT,period TEXT,released TEXT,value TEXT,PRIMARY KEY(source,series,unit,period,released))")
        db.executemany("INSERT INTO fund_macro VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING",rows)
    return len(rows)

def as_of(database, source, series, unit, cutoff):
    cutoff=date.fromisoformat(cutoff).isoformat()
    with sqlite3.connect(database) as db:
        rows=db.execute("SELECT period,released,value FROM fund_macro WHERE source=? AND series=? AND unit=? AND released<=? ORDER BY period,released",(source,series,unit,cutoff)).fetchall()
    return {period:{"released":released,"value":value} for period,released,value in rows}

def returns(start_price,end_price,start_fx,end_fx,start_cpi,end_cpi):
    """FX is target currency per asset currency; CPI is target currency economy index."""
    p0,p1,f0,f1,c0,c1=[Decimal(str(v)) for v in (start_price,end_price,start_fx,end_fx,start_cpi,end_cpi)]
    if any(not v.is_finite() or v<=0 for v in (p0,p1,f0,f1,c0,c1)):
        raise ValueError("Positive finite aligned inputs required")
    nominal=p1/p0
    fx=f1/f0
    converted=nominal*fx
    real=converted/(c1/c0)
    return {"asset_price_return_pct":str((nominal-1)*100),"fx_return_pct":str((fx-1)*100),"target_currency_return_pct":str((converted-1)*100),"real_return_pct":str((real-1)*100),"inflation_pct":str((c1/c0-1)*100),"total_return_verified":False,"alignment_verified":False,"real_orders":False}
