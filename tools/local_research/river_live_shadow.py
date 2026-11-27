"""Prospective River shadow forecasts from pending Chronos research rows.

No trading engine writes. Local journal is the only persistent model state;
a fresh estimator replays a bounded window of previously settled labels.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time

from .adaptive_review import MODELS, readonly, utc, validated
from cyberbot.db_paths import checked, pilot_path, same

VERSION = "river-live-shadow-1"
SCOPE = ("FUTURES", "BTCUSDT", "binance-usdm-public")
FEATURES = ("mean", "ar1", "chronos")
MAX_REPLAY = 1000
MAX_PENDING = 100
MAX_RECORDS = 100000
WARMUP = 60


def now_utc():
    return datetime.now(timezone.utc)


def minute(t):
    return int(t.timestamp()//60)


def digest(payload):
    return hashlib.sha256(payload.encode()).hexdigest()


def features(payload):
    p=json.loads(payload)
    if (p["mode"]!="forward_shadow_research" or p["context_bars"]!=21
            or p["prediction_bars"]!=1 or p["real_orders"] is not False
            or p["automatic_promotion"] is not False or set(p["predictions"])!=set(MODELS)):
        raise ValueError("invalid source forecast")
    values=p["predictions"]
    if any(type(v) not in (float,int) or not math.isfinite(v) or abs(v)>1000 for v in values.values()):
        raise ValueError("invalid features")
    if values["naive"]!=0:
        raise ValueError("invalid baseline")
    return {n:values[n] for n in FEATURES}


def make_model():
    from river import linear_model, preprocessing
    return preprocessing.StandardScaler() | linear_model.LinearRegression()


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS river_shadow (
        target INTEGER PRIMARY KEY, source_created TEXT NOT NULL,
        source_hash TEXT NOT NULL, created_at TEXT NOT NULL,
        features TEXT NOT NULL, prediction REAL NOT NULL,
        training_count INTEGER NOT NULL, library_version TEXT NOT NULL,
        status TEXT NOT NULL, actual REAL, settled_at TEXT
    )""")
    db.commit()


def tick(source, db, *, library_version, factory=make_model, clock=now_utc):
    """Single writer transaction; on restart replay committed labels only."""
    init(db)
    started=clock()
    current=minute(started)
    db.execute("BEGIN IMMEDIATE")
    try:
        pending=db.execute("""SELECT target,source_created,source_hash,created_at FROM river_shadow
            WHERE status='pending' AND target<? ORDER BY target LIMIT ?""",
            (current,MAX_PENDING)).fetchall()
        for target,created,fp,own_created in pending:
            row=source.execute("""SELECT target_minute,created_at,payload,outcome,status
                FROM forecasts WHERE market=? AND symbol=? AND source=? AND target_minute=?""",
                (*SCOPE,target)).fetchone()
            status,actual="unmeasurable",None
            if row and row[4]=="measured":
                validated(row[:4])
                o=json.loads(row[3])
                if (row[1]==created and digest(row[2])==fp
                        and utc(own_created)<utc(o["target_source_at"])<=clock()):
                    actual=o["actual_return_pct"]
                    status="measured"
            elif current-target<3 and (not row or row[4]=="pending"):
                continue
            db.execute("""UPDATE river_shadow SET status=?,actual=?,settled_at=?
                WHERE target=? AND status='pending'""",
                (status,actual,clock().isoformat(),target))
        db.commit()
    except BaseException:
        db.rollback()
        raise

    now=clock()
    if minute(now)!=current or now.second>35:
        return "WAIT_WINDOW"
    db.execute("BEGIN IMMEDIATE")
    try:
        if db.execute("SELECT 1 FROM river_shadow WHERE target=?",(current,)).fetchone():
            return "ALREADY_RECORDED"
        if db.execute("SELECT 1 FROM river_shadow WHERE target>? LIMIT 1",(current,)).fetchone():
            return "CLOCK_REVIEW_REQUIRED"
        if db.execute("SELECT COUNT(*) FROM river_shadow").fetchone()[0]>=MAX_RECORDS:
            return "JOURNAL_LIMIT_REACHED"
        if db.execute("SELECT 1 FROM river_shadow WHERE status='pending' LIMIT 1").fetchone():
            return "WAIT_PRIOR_OUTCOME"
        if db.execute("SELECT 1 FROM river_shadow WHERE library_version<>? LIMIT 1",
                      (library_version,)).fetchone():
            return "LIBRARY_REVIEW_REQUIRED"
        row=source.execute("""SELECT created_at,payload FROM forecasts
            WHERE market=? AND symbol=? AND source=? AND target_minute=?
            AND status='pending'""",(*SCOPE,current)).fetchone()
        if not row:
            return "WAIT_SOURCE"
        created,payload=row
        base_time=utc(created)
        if minute(base_time)!=current or base_time>now or base_time.second>35:
            return "INVALID_SOURCE_TIME"
        x=features(payload)
        history=db.execute("""SELECT target,features,actual,settled_at FROM (
            SELECT target,features,actual,settled_at FROM river_shadow
            WHERE status='measured' AND target<? AND library_version=?
            ORDER BY target DESC LIMIT ?) ORDER BY target""",
            (current,library_version,MAX_REPLAY)).fetchall()
        model=factory()
        for target,raw,y,settled in history:
            prior=json.loads(raw)
            if (minute(utc(settled))<=target or utc(settled)>now
                    or set(prior)!=set(FEATURES) or not math.isfinite(y) or y<=-100
                    or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1000
                           for v in prior.values())):
                raise ValueError("invalid replay state")
            model.learn_one(prior,y)
        pred=float(model.predict_one(x))
        if not math.isfinite(pred) or pred<=-100 or abs(pred)>1000:
            raise ValueError("invalid prediction")
        stamp=clock()
        if minute(stamp)!=current or stamp.second>35 or stamp<now:
            return "WINDOW_EXPIRED"
        # Check source again: never reconstruct a forecast from a settled row.
        latest=source.execute("""SELECT created_at,payload,status FROM forecasts
            WHERE market=? AND symbol=? AND source=? AND target_minute=?""",
            (*SCOPE,current)).fetchone()
        if latest!=(created,payload,"pending"):
            return "SOURCE_CHANGED"
        db.execute("INSERT INTO river_shadow VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (current,created,digest(payload),stamp.isoformat(),
                    json.dumps(x,sort_keys=True,allow_nan=False),pred,len(history),
                    library_version,"pending",None,None))
        finished=clock()
        if minute(finished)!=current or finished.second>35 or finished<stamp:
            return "WINDOW_EXPIRED"
        db.commit()
        return "FORECAST_RECORDED"
    finally:
        if db.in_transaction:
            db.rollback()


def status(db):
    counts=dict(db.execute("SELECT status,COUNT(*) FROM river_shadow GROUP BY status"))
    n,river,naive=db.execute("""SELECT COUNT(*),AVG(ABS(actual-prediction)),AVG(ABS(actual))
        FROM river_shadow WHERE status='measured' AND training_count>=?""",(WARMUP,)).fetchone()
    return {"version":VERSION,"scope":SCOPE,"counts":counts,"scored_after_warmup":n,
            "mae_pct":{"river":river,"naive":naive} if n else {},
            "evidence_status":"FORWARD_SHADOW_UNVERIFIED",
            "automatic_promotion":False,"profitability_verified":False,"real_orders":False}


def run(root, seconds):
    if os.environ.get("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("research rights confirmation required")
    if not 1<=seconds<=900:
        raise ValueError("invalid bounded runtime")
    from .journal_capacity import require_capacity
    require_capacity(root, 'RiverLive')
    import river
    import shutil
    from .vps_guard import MIB, MIN_FREE_DISK_MIB
    folder=root/"var/ai"
    src=folder/"forward-models-v2.sqlite3"
    path=folder/"river-live-shadow.sqlite3"
    protected=[src,*checked().values(),pilot_path(),
               *checked(root/"var/paper.sqlite3").values(),pilot_path(root/"var/paper.sqlite3")]
    if path.is_symlink() or (path.exists() and path.stat().st_nlink!=1) or any(same(path.resolve(),p.resolve()) for p in protected):
        raise ValueError("unsafe shadow path")
    with closing(readonly(src)) as source, closing(sqlite3.connect(path,timeout=3)) as db:
        deadline=time.monotonic()+seconds
        previous=None
        while True:
            require_capacity(root, 'RiverLive')
            if shutil.disk_usage(folder).free//MIB<MIN_FREE_DISK_MIB:
                raise RuntimeError("insufficient disk")
            outcome=tick(source,db,library_version=river.__version__)
            if outcome!=previous:
                print(outcome,flush=True)
                previous=outcome
            if time.monotonic()>=deadline:
                break
            time.sleep(min(2,max(0,deadline-time.monotonic())))
        return status(db)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--seconds",type=int,default=60)
    args=p.parse_args()
    print(json.dumps(run(args.root.resolve(),args.seconds),indent=2,allow_nan=False))
