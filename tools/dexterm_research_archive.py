"""Local, idempotent archive of DexTerm research reports. No network or engine writes."""
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from cyberbot.solana_pilot import address

APP_ID = 0x43594458
MAX_BYTES = 4 * 1024 * 1024
FLAGS = ("security_verified", "live_data_verified", "pilot_applied", "real_orders")

def record(kind, row, status, pool=None):
    mint = row.get("mint")
    if not address(mint) or (pool is not None and not address(pool)):
        raise ValueError("Invalid observation address")
    if not isinstance(status, str) or not 1 <= len(status) <= 80:
        raise ValueError("Invalid observation status")
    return kind, mint, pool, status

def extract(d):
    if not isinstance(d, dict) or any(d.get(k) is not False for k in FLAGS):
        raise ValueError("Unexpected research flags")
    source = d.get("source")
    if source == "dexterm_screener_query" and d.get("status") in ("diagnostic_complete","diagnostic_partial"):
        rows = d["candidates"]
        if not isinstance(rows,list) or len(rows)>10 or len(rows)!=d["candidate_count"]:
            raise ValueError("Invalid candidate count")
        return "screener", [record("screener",r,"reported_candidate") for r in rows]
    if d.get("status") == "offline_review_complete":
        rows=d["candidates"]
        if not isinstance(rows,list) or len(rows)>10 or len(rows)!=d["candidate_count"]:
            raise ValueError("Invalid review count")
        return "review", [record("review",r,r["review_status"]) for r in rows]
    if source == "dexterm_historical_shortlist_exact_mint_lookup" and d.get("status") in (
        "diagnostic_complete","diagnostic_partial","lookup_partial","no_eligible_pools","no_nonreference_candidates"):
        rows=d["lookups"]
        if not isinstance(rows,list) or len(rows)>3:
            raise ValueError("Invalid lookup count")
        obs=[]
        for r in rows:
            pool=r.get("pool")
            if pool is not None and pool["mint"]!=r["mint"]:
                raise ValueError("Pool mint mismatch")
            obs.append(record("pool_lookup",r,r["status"],pool["pool"] if pool else None))
        scan=d.get("scan")
        if scan is not None:
            if any(scan.get(k) is not False for k in FLAGS):
                raise ValueError("Unexpected scan flags")
            reports=scan["reports"]
            if not isinstance(reports,list) or len(reports)>3:
                raise ValueError("Invalid diagnostic count")
            for r in reports:
                c=r["candidate"]
                obs.append(record("snapshot",c,r["diagnostic"]["status"],c["pool"]))
        for mint in d.get("remaining_mints",[]):
            obs.append(record("lookup_pending",{"mint":mint},"not_queried"))
        return "bridge",obs
    if d.get("research_only") is True and d.get("extensions_verified") is False:
        rows=d.get("observations")
        if not isinstance(rows,list) or len(rows)>3:
            raise ValueError("Invalid extension observation count")
        if d.get("status") in ("research_complete","research_partial") and "token2022_count" in d:
            if d["token2022_count"]!=sum(r.get("status")=="token2022_observed" for r in rows):
                raise ValueError("Invalid Token-2022 count")
            return "token2022", [record("token2022",r,r["status"]) for r in rows]
        if d.get("status")=="token2022_risk_review_complete":
            if d.get("review_count")!=len(rows) or d.get("trade_eligible") is not False:
                raise ValueError("Invalid risk review")
            if any(r.get("trade_eligible") is not False for r in rows):
                raise ValueError("Unexpected risk clearance")
            return "token2022_review", [record("token2022_review",r,r["classification"]) for r in rows]
    raise ValueError("Unsupported report")

def load(path):
    with Path(path).open("rb") as f:
        data=f.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError("Report too large")
    d=json.loads(data.decode("utf-8-sig"))
    kind,rows=extract(d)
    body=json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest(),kind,body,rows

def archive(database, reports):
    db=Path(database).resolve()
    if not 1<=len(reports)<=30:raise ValueError("Report count must be 1 to 30")
    prepared=[load(p) for p in reports]
    db.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(db,timeout=10)
    inserted=0
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("BEGIN IMMEDIATE")
        app=con.execute("PRAGMA application_id").fetchone()[0]
        version=con.execute("PRAGMA user_version").fetchone()[0]
        objects=con.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if app==0 and version==0 and not objects:
            con.execute("PRAGMA application_id="+str(APP_ID))
            con.execute("PRAGMA user_version=1")
            con.execute("""CREATE TABLE research_reports(
                digest TEXT PRIMARY KEY, kind TEXT NOT NULL, imported_utc TEXT NOT NULL, payload TEXT NOT NULL)""")
            con.execute("""CREATE TABLE research_observations(
                digest TEXT NOT NULL REFERENCES research_reports(digest),
                seq INTEGER NOT NULL, kind TEXT NOT NULL, mint TEXT NOT NULL,
                pool TEXT, status TEXT NOT NULL, PRIMARY KEY(digest,seq))""")
        elif app!=APP_ID or version!=1:
            raise ValueError("Not a Cyberbot DexTerm research archive")
        stamp=datetime.now(timezone.utc).isoformat()
        for digest,kind,body,rows in prepared:
            cur=con.execute("INSERT OR IGNORE INTO research_reports VALUES (?,?,?,?)",(digest,kind,stamp,body))
            if not cur.rowcount:continue
            inserted+=1
            con.executemany("INSERT INTO research_observations VALUES (?,?,?,?,?,?)",
                            [(digest,i,*row) for i,row in enumerate(rows)])
        integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity!="ok":raise ValueError("Archive integrity failure")
        counts=dict(con.execute("SELECT kind,COUNT(*) FROM research_observations GROUP BY kind"))
        statuses=[{"kind":k,"status":s,"count":n} for k,s,n in con.execute(
            "SELECT kind,status,COUNT(*) FROM research_observations GROUP BY kind,status ORDER BY kind,status")]
        result={"status":"archive_complete","new_reports":inserted,"duplicate_reports":len(prepared)-inserted,
                "total_reports":con.execute("SELECT COUNT(*) FROM research_reports").fetchone()[0],
                "unique_mints":con.execute("SELECT COUNT(DISTINCT mint) FROM research_observations").fetchone()[0],
                "unique_pools":con.execute("SELECT COUNT(DISTINCT pool) FROM research_observations").fetchone()[0],
                "observation_counts":counts,"status_counts":statuses,"database_integrity":integrity,
                "database":str(db),"research_only":True,"network_requests":False,
                **{k:False for k in FLAGS}}
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--report",action="append",required=True)
    a=p.parse_args()
    try:
        print(json.dumps(archive(a.database,a.report),indent=2,allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,"real_orders":False,"pilot_applied":False}))
        return 1
if __name__=="__main__":raise SystemExit(main())
