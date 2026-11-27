"""Paired chronological research comparison, not a trading signal.

Chronos/base predictions were recorded before their target. LightGBM and River
are reconstructed retrospectively on those features; not live predictions.
River may learn from a completed test target only before the next target.
"""
import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
from statistics import mean

from .adaptive_review import MODELS, readonly
from .lightgbm_journal import (prepare, fit_lightgbm, FEATURES, MAX_ROWS,
                               MIN_TRAIN, MIN_TEST)
from .vps_guard import MIB, MIN_FREE_DISK_MIB

VERSION = "paired-ai-review-1"
NAMES = (*MODELS, "lightgbm", "river")


def make_river():
    from river import linear_model, preprocessing
    return preprocessing.StandardScaler() | linear_model.LinearRegression()


def predict_value(value):
    value = float(value)
    if not math.isfinite(value) or value <= -100:
        raise ValueError("invalid predicted return")
    return value


def compare(rows, *, batch_fit=fit_lightgbm, online_factory=make_river):
    train, test = prepare(rows)
    result = {"version": VERSION, "status": "INSUFFICIENT_EVIDENCE",
              "train_samples": len(train), "test_samples": len(test),
              "comparison_protocol": "same_targets_frozen_batch_online_replay",
              "evidence_status": "EXPLORATORY_UNVERIFIED",
              "gemini": "ADVISORY_ONLY_NOT_RANKED",
              "live_prediction_verified": False, "automatic_promotion": False,
              "profitability_verified": False, "real_orders": False}
    if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
        return result
    batch = list(batch_fit([r[2] for r in train], [r[3] for r in train],
                           [r[2] for r in test]))
    if len(batch) != len(test):
        raise ValueError("batch prediction count mismatch")
    online = online_factory()
    for r in train:
        online.learn_one(dict(zip(FEATURES,r[2])),r[3])
    days = defaultdict(list)
    for row, predicted in zip(test,batch):
        _,day,values,y,base = row
        x = dict(zip(FEATURES,values))
        # All retained targets are separated by at least 22 minutes.
        # Never expose this row's label before predicting and scoring.
        online_pred = predict_value(online.predict_one(x))
        errors = {**base,"lightgbm":abs(y-predict_value(predicted)),
                  "river":abs(y-online_pred)}
        if any(not math.isfinite(v) for v in errors.values()):
            raise ValueError("nonfinite error")
        days[day].append(errors)
        online.learn_one(x,y)
    scores = {n:mean(mean(e[n] for e in observations)
                     for observations in days.values()) for n in NAMES}
    result.update(status="RESEARCH_MEASURED",holdout_days=len(days),
                  first_target_minute=test[0][0],last_target_minute=test[-1][0],
                  daily_weighted_mae_pct=scores,
                  # A retrospective descriptive metric, not a selected strategy.
                  improvement_vs_naive_pct={n:100*(1-scores[n]/scores["naive"])
                      if scores["naive"] else None for n in NAMES})
    return result


def run(root):
    if os.environ.get("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED") != "1":
        raise RuntimeError("research data rights confirmation required")
    import lightgbm
    import river
    folder = root/"var/ai"
    path = folder/"paired-ai-review.sqlite3"
    if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
        raise ValueError("unsafe journal path")
    if shutil.disk_usage(folder).free//MIB < MIN_FREE_DISK_MIB:
        raise RuntimeError("insufficient disk")
    with closing(readonly(folder/"forward-models-v2.sqlite3")) as db:
        rows = db.execute("""
            SELECT target_minute,created_at,payload,outcome FROM (
                SELECT target_minute,created_at,payload,outcome FROM forecasts
                WHERE market='FUTURES' AND symbol='BTCUSDT'
                AND source='binance-usdm-public' AND status='measured'
                ORDER BY target_minute DESC LIMIT ?
            ) ORDER BY target_minute
        """,(MAX_ROWS,)).fetchall()
    versions={"lightgbm":lightgbm.__version__,"river":river.__version__}
    key=hashlib.sha256(json.dumps([VERSION,versions,rows],sort_keys=True,
                      separators=(",",":"),allow_nan=False).encode()).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS paired_reports (
            fingerprint TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
        )""")
        cached=db.execute("SELECT payload FROM paired_reports WHERE fingerprint=?",(key,)).fetchone()
        if cached:
            return {**json.loads(cached[0]),"cached":True}
        result=compare(rows)
        result.update(market="FUTURES",symbol="BTCUSDT",interval="1m",
                      source="binance-usdm-public",source_fingerprint=key,
                      versions=versions,created_at=datetime.now(timezone.utc).isoformat(),
                      cached=False)
        if rows:
            db.execute("INSERT OR IGNORE INTO paired_reports VALUES (?,?,?)",
                       (key,result["created_at"],json.dumps(result,allow_nan=False)))
            # Bound aggregate research report growth; do not touch source data.
            db.execute("""DELETE FROM paired_reports WHERE fingerprint IN (
                SELECT fingerprint FROM paired_reports ORDER BY created_at DESC,
                fingerprint DESC LIMIT -1 OFFSET 100)""")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("journal integrity failed")
        return result


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    print(json.dumps(run(p.parse_args().root.resolve()),indent=2,allow_nan=False))
