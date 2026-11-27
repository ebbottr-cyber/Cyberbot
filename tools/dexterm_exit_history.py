"""Read archived sell-only quotes and bind to original bridge observations."""
import hashlib
import json
import sqlite3
from pathlib import Path
from collections import Counter
from tools.dexterm_research_archive import APP_ID,MAX_BYTES
from tools.dexterm_paper_replay import instant,leg_amounts,window_filter
from tools.dexterm_exit_validation import validate_report
from tools.dexterm_route_accounting import USDC

def bound(entries,exits):
    counts=Counter((r["mint"],instant(r["timestamp"])) for r in entries)
    index={(r["source_digest"],r["source_index"]):r for r in entries
           if counts[(r["mint"],instant(r["timestamp"]))]==1}
    valid=[];seen=set()
    for r in exits:
        e=index.get((r["entry_source_digest"],r["entry_source_index"]))
        if e is None:continue
        if (e["mint"]!=r["mint"] or e["token_amount_raw"]!=r["token_amount_raw"]
            or instant(e["timestamp"])!=instant(r["entry_timestamp"])
            or not 180<=(instant(r["timestamp"])-instant(e["timestamp"])).total_seconds()<=3600
            or type(r["return_raw"]) is not int or r["return_raw"]<=0):
            raise ValueError("Exit does not match entry provenance")
        key=(r["entry_source_digest"],r["entry_source_index"],instant(r["timestamp"]),r["return_raw"])
        if key in seen:continue
        seen.add(key);valid.append(dict(r,exit_only=True))
    return valid

def collect_exits(database,entries,limit=500,*,window=None):
    if type(limit) is not int or not 1<=limit<=500:raise ValueError("Invalid exit report limit")
    clause,params,selection=window_filter(window)
    path=Path(database).resolve(strict=True)
    con=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=10)
    rows=[];read=0;truncated=False
    try:
        if con.execute("PRAGMA application_id").fetchone()[0]!=APP_ID or con.execute("PRAGMA user_version").fetchone()[0]!=1:
            raise ValueError("Wrong research database")
        cursor=con.execute("SELECT digest,CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END FROM research_reports WHERE kind='exit_quote'"+clause+" ORDER BY imported_utc DESC,digest DESC LIMIT ?",(MAX_BYTES,*params,limit+1))
        for digest,body in cursor:
            if read==limit:truncated=True;break
            read+=1
            if not isinstance(body,str) or hashlib.sha256(body.encode("utf-8")).hexdigest()!=digest:
                raise ValueError("Exit archive digest mismatch")
            for i,q in enumerate(validate_report(json.loads(body))):
                amount,returned,_=leg_amounts(q["sell"],q["mint"],USDC)
                rows.append({"mint":q["mint"],"timestamp":instant(q["retrieved_at"]).isoformat(),
                             "entry_timestamp":q["entry_timestamp"],"entry_source_digest":q["entry_source_digest"],
                             "entry_source_index":q["entry_source_index"],"token_amount_raw":amount,
                             "return_raw":returned,"source_digest":digest,"source_index":i,"exit_only":True})
    finally:con.close()
    valid=bound(entries,rows)
    return valid,{"exit_reports_read":read,"exit_history_truncated":truncated,
                  "bound_exit_quotes":len(valid),"unbound_or_duplicate_exit_quotes":len(rows)-len(valid),"exit_archive_import_window":selection}
