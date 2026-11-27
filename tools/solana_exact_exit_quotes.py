"""Bounded wallet-free exit quote research for recent DexTerm entry observations."""
import argparse
import json
import re
import sqlite3
import time
from collections import Counter
import httpx
from cyberbot.observed_pilot import utc
from cyberbot.providers.solana_observed import request,USDC
from cyberbot.solana_pilot import address
from tools.dexterm_research_cycle import permissions
from tools.solana_route_preview import inspect
from tools.solana_paper_replay import collect,instant,leg_amounts,FALSE_FLAGS

SOURCE="dexterm_exact_quantity_exit_quote"
MIN_AGE=180
MAX_AGE=3600
MAX_QUOTES=3

def select(rows,now,limit):
    if type(limit) is not int or not 1<=limit<=MAX_QUOTES:
        raise ValueError("Invalid quote budget")
    counts=Counter((r["mint"],instant(r["timestamp"])) for r in rows)
    ordered=sorted(rows,key=lambda r:(instant(r["timestamp"]),r["mint"],r["source_digest"],r["source_index"]))
    chosen=[];seen=set()
    for r in ordered:
        stamp=instant(r["timestamp"])
        if counts[(r["mint"],stamp)]!=1 or not MIN_AGE<=(now-stamp).total_seconds()<=MAX_AGE:continue
        key=(r["mint"],r["token_amount_raw"])
        if key in seen:continue
        seen.add(key);chosen.append(r)
        if len(chosen)==limit:break
    return chosen

def entry_ref(row):
    return {"mint":row["mint"],"entry_timestamp":row["timestamp"],
            "entry_source_digest":row["source_digest"],"entry_source_index":row["source_index"],
            "quantity_raw":str(row["token_amount_raw"])}

def validate_report(report):
    if report.get("source")!=SOURCE or report.get("research_only") is not True:
        raise ValueError("Invalid exit report source")
    if any(report.get(k) is not False for k in (*FALSE_FLAGS,"transport_mocked","quote_source_timestamp_verified","fee_semantics_verified","api_key_used")):
        raise ValueError("Unexpected exit report flags")
    status=report.get("status")
    rows=report["quotes"]
    if status not in ("exit_quotes_complete","exit_quotes_partial","no_due_entries") or not isinstance(rows,list) or len(rows)>MAX_QUOTES:
        raise ValueError("Invalid exit report")
    if status=="no_due_entries" and rows or status=="exit_quotes_complete" and not rows:
        raise ValueError("Inconsistent exit report")
    if type(report.get("attempted_quotes")) is not int or not len(rows)<=report["attempted_quotes"]<=MAX_QUOTES:
        raise ValueError("Invalid quote attempt count")
    if status=="exit_quotes_complete" and report["attempted_quotes"]!=len(rows):
        raise ValueError("Incomplete quote report")
    seen=set()
    for row in rows:
        mint=row["mint"];digest=row["entry_source_digest"];index=row["entry_source_index"]
        if not address(mint) or mint==USDC or not isinstance(digest,str) or not re.fullmatch("[0-9a-f]{64}",digest) or type(index) is not int or not 0<=index<=2:
            raise ValueError("Invalid exit provenance")
        start=instant(row["entry_timestamp"]);end=instant(row["retrieved_at"])
        if not MIN_AGE<=(end-start).total_seconds()<=MAX_AGE:raise ValueError("Exit outside research horizon")
        amount,received,delta=leg_amounts(row["sell"],mint,USDC)
        if row["quantity_raw"]!=str(amount):raise ValueError("Exit quantity mismatch")
        key=(digest,index)
        if key in seen:raise ValueError("Duplicate entry reference")
        seen.add(key)
    return rows

def run(database,*,limit=3,archive_limit=500,transport=None,clock=utc,sleep=time.sleep):
    permissions()
    if type(limit) is not int or not 1<=limit<=MAX_QUOTES:raise ValueError("Invalid quote budget")
    rows,stats=collect(database,archive_limit)
    chosen=select(rows,clock(),limit)
    out={"source":SOURCE,"status":"no_due_entries","research_only":True,
         "quotes":[],"attempted_quotes":0,"selected_entries":len(chosen),
         "stop_reason":None,"quote_source_timestamp_verified":False,"fee_semantics_verified":False,
         "api_key_used":False,"transport_mocked":transport is not None,**stats,**FALSE_FLAGS}
    if not chosen:return out
    with httpx.Client(timeout=httpx.Timeout(8,connect=6),follow_redirects=False,trust_env=False) as client:
        for i,row in enumerate(chosen):
            if i:sleep(3)
            permissions()
            started=clock()
            if not MIN_AGE<=(started-instant(row["timestamp"])).total_seconds()<=MAX_AGE:
                out["stop_reason"]="entry_outside_research_horizon";break
            mint=row["mint"];qty=row["token_amount_raw"]
            params={"inputMint":mint,"outputMint":USDC,"amount":str(qty)}
            out["attempted_quotes"]+=1
            try:
                raw=transport(params) if transport is not None else request(client,"quote",params,"")
                route=inspect(raw,mint,USDC,qty)
                leg_amounts(route,mint,USDC)
                finished=clock()
                if not 0<=(finished-started).total_seconds()<=30 or not MIN_AGE<=(finished-instant(row["timestamp"])).total_seconds()<=MAX_AGE:
                    raise ValueError("Quote outside time budget")
                out["quotes"].append(dict(entry_ref(row),retrieved_at=finished.isoformat(),sell=route))
            except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,httpx.HTTPError):
                out["stop_reason"]="quote_failed_or_invalid";break
    out["status"]="exit_quotes_complete" if len(out["quotes"])==len(chosen) else "exit_quotes_partial"
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--limit",type=int,default=3)
    a=p.parse_args()
    try:
        d=run(a.database,limit=a.limit)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 1 if d["status"]=="exit_quotes_partial" else 0
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
