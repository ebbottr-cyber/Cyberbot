"""Local research candidate lifecycle. Approval is documentation, not activation.

Approval binds to an exact prospective trial report. A changed report requires
a fresh review. Withdrawal never alters model files, trials, or trading state.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat

from .adaptive_review import readonly, utc
from .journal_capacity import safe_stat, SUFFIXES
from .model_registry import canonical, sha, validate, MAX_CANDIDATES
from .challenger_shadow import status as trial_status
from .vps_guard import MIB, MIN_FREE_DISK_MIB

NAME="ai-model-lifecycle.sqlite3"
REGISTRY="candidate-models.sqlite3"
MAX_BYTES=8*MIB
MAX_EVENTS=1000
SCOPE="FUTURES/BTCUSDT/binance-usdm-public"


def paths(root,name):
    folder=Path(root)/"var/ai"
    for p in (folder.parent,folder):
        s=safe_stat(p)
        if s is None or not stat.S_ISDIR(s.st_mode):
            raise ValueError("research folder required")
    path=folder/name
    total=0
    for suffix in SUFFIXES:
        s=safe_stat(Path(str(path)+suffix))
        if s is not None:
            if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:
                raise ValueError("unsafe lifecycle journal")
            total+=s.st_size
    return path,total


def registry(root):
    path,total=paths(root,REGISTRY)
    if safe_stat(path) is None:
        return {}
    if total>64*MIB:
        raise ValueError("oversized candidate store")
    with closing(readonly(path)) as db:
        rows=db.execute("SELECT candidate,metadata,model_text FROM model_candidates ORDER BY candidate LIMIT ?",
                        (MAX_CANDIDATES+1,)).fetchall()
    if len(rows)>MAX_CANDIDATES:
        raise ValueError("candidate capacity exceeded")
    output={}
    for cid,raw,text in rows:
        meta=json.loads(raw)
        if validate(meta,text)!=cid:
            raise ValueError("candidate integrity mismatch")
        output[cid]={k:meta[k] for k in ("model","library_version","train_samples",
                    "test_samples","last_train_target","first_test_target","model_mae_pct","naive_mae_pct")}
    return output


def evidence(trial,cid):
    if (trial.get("status")!="REVIEW_ONLY" or trial.get("candidate")!=cid
            or trial.get("version")!="champion-challenger-1" or trial.get("scope")!=SCOPE
            or trial.get("reference")!="chronos" or trial.get("challenger")!="lightgbm"
            or any(trial.get(k) is not False for k in ("production_champion",
                   "automatic_promotion","real_orders","paper_readiness_verified","profitability_verified"))):
        return None
    counts=trial["counts"]
    scores=trial["daily_weighted_mae_pct"]
    import math
    if (type(counts["retained"]) is not int or counts["retained"]<60
            or type(trial["utc_days"]) is not int or trial["utc_days"]<10
            or set(scores)!={"chronos","lightgbm","naive"}
            or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in scores.values())
            or min(scores["chronos"],scores["naive"])<=0
            or scores["lightgbm"]>.95*min(scores["chronos"],scores["naive"])):
        return None
    return sha(canonical(trial).encode())


def events(db):
    rows=db.execute("SELECT candidate,action,evidence_sha,recorded_at FROM events ORDER BY id LIMIT ?",
                    (MAX_EVENTS+1,)).fetchall()
    if len(rows)>MAX_EVENTS:
        raise ValueError("event capacity exceeded")
    latest={}
    previous=None
    for cid,action,fp,stamp in rows:
        when=utc(stamp)
        if (not re.fullmatch("[a-f0-9]{64}",cid) or action not in ("APPROVE_RESEARCH","WITHDRAW_RESEARCH")
                or not re.fullmatch("[a-f0-9]{64}",fp) or when>datetime.now(timezone.utc)
                or (previous is not None and when<previous)):
            raise ValueError("invalid lifecycle event")
        prior=latest.get(cid)
        if action=="WITHDRAW_RESEARCH" and (not prior or prior["action"]!="APPROVE_RESEARCH" or prior["evidence_sha"]!=fp):
            raise ValueError("withdrawal without approval")
        latest[cid]={"action":action,"evidence_sha":fp,"recorded_at_utc":when.isoformat()}
        previous=when
    return latest,len(rows)


def describe(candidates,trial,latest):
    rows=[]
    for cid,meta in sorted(candidates.items()):
        state="REGISTERED_INTEGRITY_CHECKED"
        fp=None
        if trial.get("candidate")==cid:
            state="TRIAL_REVIEW_REQUIRED" if trial.get("status")=="DATA_REVIEW_REQUIRED" else "PROSPECTIVE_TRIAL"
            fp=evidence(trial,cid)
            if fp:
                state="AWAITING_HUMAN_REVIEW"
        event=latest.get(cid)
        if event:
            if event["action"]=="WITHDRAW_RESEARCH":
                state="RESEARCH_APPROVAL_WITHDRAWN"
            elif fp and fp==event["evidence_sha"]:
                state="RESEARCH_APPROVED"
            else:
                state="REVIEW_REFRESH_REQUIRED"
        rows.append({"candidate":cid,"state":state,**meta,"last_review":event})
    return rows


def status(root, *, trial=None):
    base={"version":"ai-model-lifecycle-1","automatic_promotion":False,
          "production_activation":False,"paper_readiness_verified":False,
          "real_orders":False,"automatic_deletion":False}
    try:
        folder=Path(root)/"var/ai"
        for p in (folder.parent,folder):
            if safe_stat(p) is None:
                return {**base,"status":"NOT_AVAILABLE","candidates":[]}
        candidates=registry(root)
        trial=trial_status(root) if trial is None else trial
        path,total=paths(root,NAME)
        latest,count={},0
        if total>=MAX_BYTES:
            return {**base,"status":"LIMIT_REACHED","candidates":[]}
        if safe_stat(path) is not None:
            with closing(readonly(path)) as db:
                latest,count=events(db)
        if set(latest)-set(candidates):
            raise ValueError("review refers to missing candidate")
        return {**base,"status":"LIMIT_REACHED" if count>=MAX_EVENTS else "AVAILABLE",
                "event_count":count,"candidates":describe(candidates,trial,latest)}
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return {**base,"status":"DATA_REVIEW_REQUIRED","candidates":[]}


def record(root,cid,action,*,confirmed=False):
    if not confirmed or os.getenv("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("explicit research-only confirmation required")
    if action not in ("APPROVE_RESEARCH","WITHDRAW_RESEARCH") or not re.fullmatch("[a-f0-9]{64}",cid):
        raise ValueError("invalid review request")
    if cid not in registry(root):
        raise ValueError("candidate missing")
    path,total=paths(root,NAME)
    if total>=MAX_BYTES or shutil.disk_usage(path.parent).free<MIN_FREE_DISK_MIB*MIB:
        return {"status":"WAIT_CAPACITY","real_orders":False}
    with closing(sqlite3.connect(path,timeout=5)) as db,db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,candidate TEXT NOT NULL,action TEXT NOT NULL,
            evidence_sha TEXT NOT NULL,recorded_at TEXT NOT NULL)""")
        latest,count=events(db)
        prior=latest.get(cid)
        if action=="APPROVE_RESEARCH":
            fp=evidence(trial_status(root),cid)
            if not fp:
                raise ValueError("prospective review evidence insufficient")
            if prior and prior["action"]==action and prior["evidence_sha"]==fp:
                return {"status":"UNCHANGED","real_orders":False}
        else:
            if not prior or prior["action"]!="APPROVE_RESEARCH":
                raise ValueError("no approval to withdraw")
            fp=prior["evidence_sha"]
        if count>=MAX_EVENTS:
            return {"status":"WAIT_CAPACITY","real_orders":False}
        stamp=datetime.now(timezone.utc)
        previous=db.execute("SELECT recorded_at FROM events ORDER BY id DESC LIMIT 1").fetchone()
        if previous and stamp<utc(previous[0]):
            raise ValueError("clock moved backwards")
        db.execute("INSERT INTO events (candidate,action,evidence_sha,recorded_at) VALUES (?,?,?,?)",
                   (cid,action,fp,stamp.isoformat()))
    return {"status":"RECORDED","action":action,"candidate":cid,
            "automatic_promotion":False,"production_activation":False,"real_orders":False}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    g=p.add_mutually_exclusive_group()
    g.add_argument("--approve")
    g.add_argument("--withdraw")
    p.add_argument("--confirm-research-only",action="store_true")
    args=p.parse_args()
    cid=args.approve or args.withdraw
    result=record(args.root,cid,"APPROVE_RESEARCH" if args.approve else "WITHDRAW_RESEARCH",
                  confirmed=args.confirm_research_only) if cid else status(args.root)
    print(json.dumps(result,indent=2,allow_nan=False))
