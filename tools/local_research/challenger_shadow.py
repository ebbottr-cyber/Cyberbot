"""One explicit local prospective challenger trial; no production champion.

Chronos is the research comparator. A trusted locally registered LightGBM
candidate is frozen for the trial. Forecasts are recorded before settlement;
scoring rechecks the original source payload and target timing. No promotion.
"""
import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
from statistics import mean

from .adaptive_review import readonly, utc, validated
from .journal_capacity import safe_stat, SUFFIXES
from .river_live_shadow import features, digest
from .model_registry import read, FEATURES
from .vps_guard import MIB, MIN_FREE_DISK_MIB

NAME="challenger-shadow.sqlite3"
SCOPE=("FUTURES","BTCUSDT","binance-usdm-public")
MAX_BYTES=32*MIB
MAX_ROWS=10000
MIN_BLOCKS=60
MIN_DAYS=10
SPACING=22


def clock():
    return datetime.now(timezone.utc)


def minute(t):
    return int(t.timestamp()//60)


def paths(root):
    folder=Path(root)/"var/ai"
    for item in (folder.parent,folder):
        s=safe_stat(item)
        if s is None or not stat.S_ISDIR(s.st_mode):
            raise ValueError("existing research folder required")
    source=folder/"forward-models-v2.sqlite3"
    dest=folder/NAME
    total=0
    for p in (source,dest):
        for suffix in SUFFIXES:
            s=safe_stat(Path(str(p)+suffix))
            if s is None:
                if p==source and not suffix:
                    raise ValueError("forward journal required")
                continue
            if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:
                raise ValueError("unsafe journal")
            if p==dest:
                total+=s.st_size
    return source,dest,total


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS trial (
        id INTEGER PRIMARY KEY CHECK(id=1), candidate TEXT NOT NULL,
        started_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS forecasts (
        target INTEGER PRIMARY KEY, source_created TEXT NOT NULL,
        source_hash TEXT NOT NULL, created_at TEXT NOT NULL,
        prediction REAL NOT NULL)""")


def source_row(source,target):
    return source.execute("""SELECT created_at,payload,status,outcome FROM forecasts
        WHERE market=? AND symbol=? AND source=? AND target_minute=?""",
        (*SCOPE,target)).fetchone()


def tick(source,db,candidate,predict,*,now=clock):
    if not isinstance(candidate,str) or not re.fullmatch("[a-f0-9]{64}",candidate):
        raise ValueError("invalid candidate id")
    start=now()
    db.execute("BEGIN IMMEDIATE")
    try:
        init(db)
        trial=db.execute("SELECT candidate,started_at FROM trial WHERE id=1").fetchone()
        if trial is None:
            db.execute("INSERT INTO trial VALUES (1,?,?)",(candidate,start.isoformat()))
            db.commit()
            return "TRIAL_REGISTERED"
        if trial[0]!=candidate:
            raise ValueError("existing frozen candidate; manual review required")
        registered=utc(trial[1])
        current=minute(start)
        if registered>start:
            raise ValueError("clock moved backwards")
        if current<=minute(registered) or start.second>35:
            return "WAIT_WINDOW"
        if db.execute("SELECT 1 FROM forecasts WHERE target>=?",(current,)).fetchone():
            return "ALREADY_RECORDED_OR_CLOCK_REVIEW"
        if db.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]>=MAX_ROWS:
            return "WAIT_CAPACITY"
        row=source_row(source,current)
        if not row or row[2]!="pending" or row[3] is not None:
            return "WAIT_SOURCE"
        created,payload=row[:2]
        source_time=utc(created)
        if minute(source_time)!=current or source_time>start or source_time.second>35:
            raise ValueError("invalid source timing")
        x=features(payload)
        prediction=float(predict([x[n] for n in FEATURES]))
        if not math.isfinite(prediction) or not -100<prediction<=1000:
            raise ValueError("invalid candidate forecast")
        stamp=now()
        if minute(stamp)!=current or stamp.second>35 or stamp<start:
            return "WINDOW_EXPIRED"
        if source_row(source,current)!=row:
            return "SOURCE_CHANGED"
        db.execute("INSERT INTO forecasts VALUES (?,?,?,?,?)",
                   (current,created,digest(payload),stamp.isoformat(),prediction))
        finish=now()
        if minute(finish)!=current or finish.second>35 or finish<stamp:
            return "WINDOW_EXPIRED"
        db.commit()
        return "FORECAST_RECORDED"
    finally:
        if db.in_transaction:
            db.rollback()


def summarize(source,db,*,now=None):
    now=now or clock()
    base={"version":"champion-challenger-1","scope":"/".join(SCOPE),
          "reference":"chronos","challenger":"lightgbm","production_champion":False,
          "automatic_promotion":False,"profitability_verified":False,
          "paper_readiness_verified":False,"real_orders":False}
    trial=db.execute("SELECT candidate,started_at FROM trial WHERE id=1").fetchone()
    if not trial:
        return {**base,"status":"NO_TRIAL"}
    if not re.fullmatch("[a-f0-9]{64}",trial[0]):
        raise ValueError("invalid trial identity")
    registered=utc(trial[1])
    if registered>now:
        raise ValueError("future trial")
    days=defaultdict(list)
    counts={"pending":0,"unmeasurable":0,"measured":0,"retained":0}
    last=None
    rows=db.execute("SELECT target,source_created,source_hash,created_at,prediction FROM forecasts ORDER BY target LIMIT ?",(MAX_ROWS+1,)).fetchall()
    if len(rows)>MAX_ROWS:
        raise ValueError("trial capacity exceeded")
    for target,created,fp,own,pred in rows:
        stamp=utc(own)
        if (type(target) is not int or target<=minute(registered) or minute(stamp)!=target
                or stamp.second>35 or stamp>now or not utc(created)<=stamp
                or not math.isfinite(pred) or not -100<pred<=1000):
            raise ValueError("invalid challenger timing or prediction")
        row=source_row(source,target)
        if not row or row[0]!=created or digest(row[1])!=fp:
            raise ValueError("missing or changed source")
        if row[2] not in ("pending","unmeasurable","measured"):
            raise ValueError("invalid source status")
        counts[row[2]]+=1
        if row[2]!="measured":
            continue
        _,day,errors=validated((target,created,row[1],row[3]))
        outcome=json.loads(row[3])
        if not stamp<utc(outcome["target_source_at"])<=now:
            raise ValueError("challenger not before outcome")
        if last is not None and target-last<SPACING:
            continue
        last=target
        counts["retained"]+=1
        e=abs(outcome["actual_return_pct"]-pred)
        if not math.isfinite(e) or e>1e6 or max(errors.values())>1e6:
            raise ValueError("invalid error")
        days[day].append((errors["chronos"],e,errors["naive"]))
    result={**base,"status":"INSUFFICIENT_EVIDENCE","candidate":trial[0],
            "trial_started_at_utc":registered.isoformat(),"counts":counts,"utc_days":len(days),
            "min_blocks":MIN_BLOCKS,"min_days":MIN_DAYS,"spacing_minutes":SPACING}
    if days:
        a,b,c=[mean(mean(v[i] for v in group) for group in days.values()) for i in range(3)]
        result["daily_weighted_mae_pct"]={"chronos":a,"lightgbm":b,"naive":c}
        if counts["retained"]>=MIN_BLOCKS and len(days)>=MIN_DAYS:
            result["status"]="REVIEW_ONLY" if min(a,c)>0 and b<=.95*min(a,c) else "NO_CLEAR_ADVANTAGE"
    return result


def status(root):
    base={"automatic_promotion":False,"real_orders":False,"paper_readiness_verified":False}
    try:
        dest=Path(root)/"var/ai"/NAME
        for p in (dest.parent.parent,dest.parent,dest):
            if safe_stat(p) is None:
                return {**base,"status":"NOT_AVAILABLE"}
        source,dest,total=paths(root)
        if total>=MAX_BYTES:
            return {**base,"status":"LIMIT_REACHED"}
        with closing(readonly(source)) as src,closing(readonly(dest)) as db:
            src.execute("BEGIN")
            db.execute("BEGIN")
            return summarize(src,db)
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return {**base,"status":"DATA_REVIEW_REQUIRED"}


def run(root,candidate):
    if os.getenv("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("research rights confirmation required")
    source,dest,total=paths(root)
    if total>=MAX_BYTES or shutil.disk_usage(dest.parent).free<MIN_FREE_DISK_MIB*MIB:
        return {"status":"WAIT_CAPACITY","real_orders":False}
    # Explicitly selected trusted local model only; no network or pickle loading.
    import lightgbm as lgb
    import numpy as np
    meta,text=read(root,candidate,lgb.__version__)
    if meta["last_train_target"]>=minute(clock()):
        raise ValueError("candidate training boundary is not historical")
    model=lgb.Booster(model_str=text)
    with closing(readonly(source)) as src,closing(sqlite3.connect(dest,timeout=3)) as db:
        action=tick(src,db,candidate,lambda x:model.predict(np.asarray([x]),num_threads=2)[0])
    return {"status":action,"automatic_promotion":False,"real_orders":False}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--candidate",help="explicit trusted local candidate id; omit for read-only status")
    args=p.parse_args()
    print(json.dumps(run(args.root,args.candidate) if args.candidate else status(args.root),
                     indent=2,allow_nan=False))
