"""Bounded, explicit local research decision journal; dashboard reads never write."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat

from .adaptive_review import readonly, utc
from .ai_risk_referee import CANDIDATES, SCOPE
from .journal_capacity import safe_stat, SUFFIXES
from .vps_guard import MIB, MIN_FREE_DISK_MIB

NAME="ai-decision-memory.sqlite3"
MAX_BYTES=16*MIB
MAX_ROWS=10000
HISTORY_LIMIT=50
CHECKS=("research_only_flags","scope_match","candidate_evidence","forward_evidence",
        "degradation_review","forecast_quality","forecast_freshness","journal_capacity",
        "scheduler_health")
INVALID="invalid_or_missing_diagnostics"


def packet(snapshot):
    risk=snapshot["risk_referee"]
    if (risk["version"]!="ai-risk-referee-1" or risk["scope"]!=SCOPE
            or any(risk[k] is not False for k in ("real_orders","automatic_promotion",
                  "paper_readiness_verified","execution_risk_verified"))):
        raise ValueError("invalid research decision")
    candidate=risk["review_candidate"]
    proposed=snapshot["model_referee"].get("review_candidate")
    proposed=proposed if proposed in CANDIDATES else None
    checks=risk["checks"]
    reasons=risk["failed_checks"]
    status=risk["status"]
    if (not isinstance(checks,dict) or not set(checks)<=set(CHECKS)
            or any(type(v) is not bool for v in checks.values())
            or not isinstance(reasons,list) or len(set(reasons))!=len(reasons)
            or not set(reasons)<=set(CHECKS)|{INVALID}
            or set(reasons)-{INVALID}!={k for k,v in checks.items() if not v}):
        raise ValueError("invalid risk checks")
    if status=="HUMAN_REVIEW_ONLY":
        if set(checks)!=set(CHECKS) or reasons or candidate not in CANDIDATES or candidate!=proposed:
            raise ValueError("invalid review approval")
    elif status=="REVIEW_BLOCKED":
        if not reasons or candidate is not None:
            raise ValueError("invalid blocked decision")
    else:
        raise ValueError("unknown risk decision")
    return {"scope":SCOPE,"status":status,"proposed_candidate":proposed,
            "review_candidate":candidate,"failed_checks":sorted(reasons),
            "checks":{k:checks[k] for k in sorted(checks)},
            "automatic_promotion":False,"real_orders":False}


def location(root):
    path=Path(root)/"var/ai"/NAME
    for parent in (path.parent.parent,path.parent):
        s=safe_stat(parent)
        if s is None or not stat.S_ISDIR(s.st_mode):
            raise ValueError("existing local research directory required")
    total=0
    for suffix in SUFFIXES:
        s=safe_stat(Path(str(path)+suffix))
        if s is not None:
            if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:
                raise ValueError("unsafe decision journal")
            total+=s.st_size
    return path,total


def canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False)


def record(root,snapshot,*,now=None):
    if os.getenv("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("local research rights confirmation required")
    data=packet(snapshot)
    payload=canonical(data)
    digest=hashlib.sha256(payload.encode()).hexdigest()
    path,total=location(root)
    if total>=MAX_BYTES or shutil.disk_usage(path.parent).free<MIN_FREE_DISK_MIB*MIB:
        return {"status":"WAIT_DECISION_CAPACITY","recorded":False}
    stamp=(now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    with closing(sqlite3.connect(path,timeout=5)) as db,db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY, evaluated_at TEXT NOT NULL,
            fingerprint TEXT NOT NULL, payload TEXT NOT NULL)""")
        cols=tuple(r[1] for r in db.execute("PRAGMA table_info(decisions)"))
        if cols!=("id","evaluated_at","fingerprint","payload"):
            raise ValueError("unexpected decision schema")
        last=db.execute("SELECT evaluated_at,fingerprint,payload FROM decisions ORDER BY id DESC LIMIT 1").fetchone()
        if last:
            if utc(last[0])>utc(stamp) or hashlib.sha256(last[2].encode()).hexdigest()!=last[1]:
                raise ValueError("decision history requires review")
            if last[1]==digest:
                return {"status":"UNCHANGED_DECISION","recorded":False}
        if db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]>=MAX_ROWS:
            return {"status":"WAIT_DECISION_CAPACITY","recorded":False}
        db.execute("INSERT INTO decisions (evaluated_at,fingerprint,payload) VALUES (?,?,?)",
                   (stamp,digest,payload))
    return {"status":"RECORDED","recorded":True,"decision":data}


def history(root):
    base={"version":"ai-decision-memory-1","records":[],"automatic_deletion":False,
          "automatic_promotion":False,"real_orders":False,"tamper_proof":False}
    try:
        path=Path(root)/"var/ai"/NAME
        for p in (path.parent.parent,path.parent,path):
            if safe_stat(p) is None:
                return {**base,"status":"NOT_AVAILABLE"}
        path,total=location(root)
        if total>=MAX_BYTES:
            return {**base,"status":"LIMIT_REACHED"}
        with closing(readonly(path)) as db:
            rows=db.execute("""SELECT evaluated_at,fingerprint,payload FROM decisions
                ORDER BY id DESC LIMIT ?""",(HISTORY_LIMIT,)).fetchall()
            count=db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        records=[]
        for stamp,digest,raw in rows:
            if len(raw)>4096 or hashlib.sha256(raw.encode()).hexdigest()!=digest:
                raise ValueError("decision checksum mismatch")
            date=utc(stamp)
            if date>datetime.now(timezone.utc):
                raise ValueError("future decision")
            p=json.loads(raw)
            # Revalidate and expose only known fields.
            risk={**p,"version":"ai-risk-referee-1","paper_readiness_verified":False,
                  "execution_risk_verified":False}
            clean=packet({"risk_referee":risk,"model_referee":{"review_candidate":p["proposed_candidate"]}})
            if clean!=p:
                raise ValueError("unexpected decision fields")
            records.append({"evaluated_at_utc":date.isoformat(),**clean})
        return {**base,"status":"LIMIT_REACHED" if count>=MAX_ROWS else "AVAILABLE",
                "records":records,"total_records":count,"bytes":total,
                "max_records":MAX_ROWS,"admission_limit_bytes":MAX_BYTES}
    except (OSError,sqlite3.Error,ValueError,KeyError,TypeError,AttributeError,OverflowError):
        return {**base,"status":"DATA_REVIEW_REQUIRED"}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--record",action="store_true")
    args=p.parse_args()
    if args.record:
        from .ai_dashboard import snapshot
        result=record(args.root,snapshot(args.root))
    else:
        result=history(args.root)
    print(json.dumps(result,indent=2,allow_nan=False))
    if result["status"]=="WAIT_DECISION_CAPACITY":
        raise SystemExit(75)


if __name__=="__main__":
    main()
