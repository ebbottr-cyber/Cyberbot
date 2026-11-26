"""Read-only summaries of locally supplied research archive reports, not live prices."""
import json
from pathlib import Path

LIMIT=8_000_000
TARGETS={"BIST":803,"NASDAQ":3400,"XETRA":1749}

def read(path):
    if not path: raise ValueError("not configured")
    with Path(path).open("rb") as f:
        raw=f.read(LIMIT+1)
    if len(raw)>LIMIT: raise ValueError("report too large")
    d=json.loads(raw)
    if not isinstance(d,dict):raise ValueError("report schema")
    return d

def number(x):
    if type(x) is not int or x<0:raise ValueError("invalid count")
    return x

def result(m,d,nasdaq=False):
    target=TARGETS[m]
    if nasdaq:
        count=number(d["candidates"]); attempted=number(d["attempted"])
        downloaded=number(d["downloaded"]); bars=number(d["bars_5m"])
        missing=d["missing_or_failed"]
    else:
        count=number(d["target"]); attempted=number(d["attempted"])
        downloaded=number(d["downloaded"]); bars=number(d["rows"])
        missing=d["missing"]
    if count!=target or not downloaded<=attempted<=target or bars<downloaded:
        raise ValueError("inconsistent counts")
    if not isinstance(missing,list) or len(missing)!=target-downloaded:
        raise ValueError("missing count")
    if any(not isinstance(s,str) or not 1<=len(s)<=24 or not s.isascii() or not all(c.isalnum() or c in ".-_" for c in s) for s in missing):
        raise ValueError("invalid symbol")
    if len(set(missing))!=len(missing):raise ValueError("duplicate symbol")
    return {"market":m,"target":target,"attempted":attempted,"downloaded":downloaded,
            "bars_5m":bars,"missing":sorted(missing),"status":"report_only",
            "source":"Syncster" if nasdaq else "Yahoo Finance",
            "coverage_pct":round(100*downloaded/target,2)}

def coverage_5m(nasdaq_path=None,bist_xetra_path=None):
    markets={}
    for market,target in TARGETS.items():
        markets[market]={"market":market,"target":target,"attempted":None,"downloaded":None,
                         "bars_5m":None,"missing":None,"coverage_pct":None,"status":"unavailable",
                         "source":"Syncster" if market=="NASDAQ" else "Yahoo Finance"}
    try: markets["NASDAQ"]=result("NASDAQ",read(nasdaq_path),True)
    except (OSError,ValueError,TypeError,KeyError):pass
    try:
        doc=read(bist_xetra_path)
        for m in ("BIST","XETRA"):
            try:markets[m]=result(m,doc[m])
            except (ValueError,TypeError,KeyError):pass
    except (OSError,ValueError,TypeError,KeyError):pass
    return {"interval":"5m","markets":markets,"report_only":True,"live_progress":False,
            "archive_files_verified":False,"license_verified":False,"execution_enabled":False}
