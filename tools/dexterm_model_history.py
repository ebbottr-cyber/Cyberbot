"""Separate SQLite research experiment history. No model state or production changes."""
import argparse
import json
import os
import re
import sqlite3
from datetime import datetime,timezone
from pathlib import Path
from tools.dexterm_gemini_review import prepare,digest,load,count,number
from tools.dexterm_paper_replay import FALSE_FLAGS

APP_ID=0x43594D48
VERSION=1
MAX_RECORDS=10000
STATUS={"not_requested","blocked_by_experiment_gate","unavailable_or_failed","experiment_complete"}

def normalize(report):
    packet=prepare(report)
    dataset=report["dataset_sha256"]
    if not isinstance(dataset,str) or not re.fullmatch("[0-9a-f]{64}",dataset):
        raise ValueError("Invalid dataset digest")
    statuses={k:report[k] for k in ("lightgbm_status","river_status")}
    if any(v not in STATUS for v in statuses.values()):raise ValueError("Invalid optional model status")
    body=packet["summary"]
    names={m["model"] for m in body["models"]}
    for key,name in (("lightgbm_status","lightgbm"),("river_status","river_logistic")):
        if (statuses[key]=="experiment_complete")!=(name in names):
            raise ValueError("Optional model status mismatch")
    c=report["consensus"]
    if c.get("trade_eligible") is not False:raise ValueError("Unexpected consensus authority")
    status=c.get("status")
    if status not in ("blocked_by_experiment_gate","consensus_blocked","consensus_diagnostic_complete"):
        raise ValueError("Invalid consensus status")
    consensus={"status":status}
    if status=="consensus_diagnostic_complete":
        if not {"logistic_baseline","lightgbm"}<=names:raise ValueError("Missing consensus models")
        keys=("joint_positive","joint_nonpositive","disagreement","uncertain")
        counts={k:count(c["counts"][k]) for k in keys}
        n=count(c["sample_count"]);covered=count(c["covered_samples"])
        if not n or sum(counts.values())!=n or covered!=counts["joint_positive"]+counts["joint_nonpositive"] or count(c["abstained_samples"])!=n-covered:
            raise ValueError("Invalid consensus counts")
        if any(m["samples"]!=n for m in body["models"]):raise ValueError("Unaligned sample counts")
        acc=c["covered_accuracy"]
        if (covered==0)!=(acc is None):raise ValueError("Invalid covered accuracy")
        consensus.update(counts=counts,sample_count=n,covered_samples=covered,
                         covered_accuracy=None if acc is None else number(acc,1),
                         mean_probability_brier=number(c["mean_probability_brier"],1))
    normalized={"schema_version":VERSION,"dataset_sha256":dataset,"summary":body,
                "optional_model_status":statuses,"consensus":consensus}
    # Older experiment reports remain readable. Store only aggregate adaptive
    # diagnostics, never the per-token trace or candidate probabilities.
    a=report.get("adaptive_weights")
    if a is not None:
        if not isinstance(a,dict) or a.get("trade_eligible") is not False:
            raise ValueError("Unexpected adaptive authority")
        status=a.get("status")
        if status not in ("not_requested","blocked_by_experiment_gate","adaptive_weights_blocked",
                          "invalid_replay_inputs","adaptive_weights_diagnostic_complete"):
            raise ValueError("Invalid adaptive status")
        adaptive={"status":status}
        if status=="adaptive_weights_diagnostic_complete":
            if a.get("weights_updated") is not False or a.get("model_promoted") is not False:
                raise ValueError("Unexpected adaptive weight change")
            n=count(a["sample_count"]);adapted=count(a["adaptive_samples"])
            if not n or adapted>n or not {"logistic_baseline","lightgbm"}<=names or any(m["samples"]!=n for m in body["models"]):
                raise ValueError("Invalid adaptive sample count")
            adaptive.update(sample_count=n,adaptive_samples=adapted,
                            adaptive_brier=number(a["adaptive_brier"],1),
                            equal_weight_brier=number(a["equal_weight_brier"],1))
        normalized["adaptive"]=adaptive
    return normalized

def connect(path,*,write=False):
    path=Path(path).expanduser().resolve()
    created=False
    if write and not path.exists():
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            os.close(fd);created=True
        except FileExistsError:pass
    con=sqlite3.connect(path.as_uri()+("?mode=rw" if write else "?mode=ro"),uri=True,timeout=10)
    try:
        if created:
            with con:
                con.execute("BEGIN IMMEDIATE")
                con.execute("CREATE TABLE experiments (id TEXT PRIMARY KEY, dataset_sha256 TEXT NOT NULL, recorded_utc TEXT NOT NULL, payload TEXT NOT NULL)")
                con.execute("CREATE INDEX experiments_dataset ON experiments(dataset_sha256)")
                con.execute(f"PRAGMA application_id={APP_ID}")
                con.execute(f"PRAGMA user_version={VERSION}")
        if con.execute("PRAGMA application_id").fetchone()[0]!=APP_ID or con.execute("PRAGMA user_version").fetchone()[0]!=VERSION:
            raise ValueError("Wrong model history database")
        if con.execute("PRAGMA quick_check").fetchall()!=[("ok",)]:raise ValueError("Database integrity failed")
        return con
    except Exception:
        con.close()
        raise

def archive(path,report):
    body=normalize(report);key=digest(body)
    payload=json.dumps(body,sort_keys=True,separators=(",",":"),allow_nan=False)
    con=connect(path,write=True)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            duplicate=con.execute("SELECT 1 FROM experiments WHERE id=?",(key,)).fetchone() is not None
            if not duplicate:
                if con.execute("SELECT count(*) FROM experiments").fetchone()[0]>=MAX_RECORDS:
                    raise ValueError("History capacity reached; no automatic deletion")
                con.execute("INSERT INTO experiments VALUES (?,?,?,?)",(key,body["dataset_sha256"],datetime.now(timezone.utc).isoformat(),payload))
        return {"status":"duplicate_ignored" if duplicate else "experiment_archived","experiment_id":key,
                "research_only":True,"weights_updated":False,"model_promoted":False,**FALSE_FLAGS}
    finally:con.close()

def history(path,*,limit=100):
    if type(limit) is not int or not 1<=limit<=500:raise ValueError("Invalid history limit")
    con=connect(path)
    try:
        total,distinct=con.execute("SELECT count(*),count(DISTINCT dataset_sha256) FROM experiments").fetchone()
        rows=con.execute("SELECT id,dataset_sha256,recorded_utc,payload FROM experiments ORDER BY recorded_utc DESC,id DESC LIMIT ?",(limit,)).fetchall()
        records=[]
        for key,ds,stamp,payload in rows:
            body=json.loads(payload)
            if digest(body)!=key or body.get("dataset_sha256")!=ds:raise ValueError("History digest mismatch")
            records.append({"experiment_id":key,"recorded_utc":stamp,**body})
        return {"status":"history_read","total_experiments":total,"distinct_dataset_digests":distinct,
                "history_truncated":total>limit,"records":records,"research_only":True,
                "independent_datasets_verified":False,"performance_improvement_verified":False,
                "weights_updated":False,"model_promoted":False,**FALSE_FLAGS}
    finally:con.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history-database",required=True)
    p.add_argument("--experiment-report")
    p.add_argument("--limit",type=int,default=100)
    a=p.parse_args()
    try:
        result=archive(a.history_database,load(a.experiment_report)) if a.experiment_report else history(a.history_database,limit=a.limit)
        print(json.dumps(result,indent=2,allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
