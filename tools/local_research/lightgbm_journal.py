"""Bounded CPU training on previously settled Futures research forecasts.

This is retrospective model comparison, not a live forecast. No model
promotion, external API call, or trading engine write.
"""
import argparse
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

from .adaptive_review import validated, readonly, MODELS
from .vps_guard import MIB, MIN_FREE_DISK_MIB

VERSION = "lightgbm-forward-review-1"
MAX_ROWS = 10000
SPACING = 22
MIN_TRAIN = 60
MIN_TEST = 20
FEATURES = ("mean", "ar1", "chronos")


def prepare(rows):
    kept = []
    seen = None
    for row in rows:
        minute, day, errors = validated(row)
        if seen is not None and minute <= seen:
            raise ValueError("duplicate or unordered target")
        seen = minute
        if kept and minute-kept[-1][0] < SPACING:
            continue
        p, o = json.loads(row[2]), json.loads(row[3])
        kept.append((minute, day, [p["predictions"][n] for n in FEATURES],
                     o["actual_return_pct"], errors))
    days = sorted({r[1] for r in kept})
    if len(days) < 10:
        return [], []
    holdout = set(days[len(days)*7//10:])
    train = [r for r in kept if r[1] not in holdout]
    test = [r for r in kept if r[1] in holdout]
    return train, test


def train_lightgbm(train_x, train_y):
    import lightgbm as lgb
    import numpy as np
    model = lgb.train(
        {"objective": "regression_l1", "num_threads": 2,
         "verbosity": -1, "seed": 42, "deterministic": True,
         "force_col_wise": True, "num_leaves": 7,
         "min_data_in_leaf": 10, "learning_rate": 0.05},
        lgb.Dataset(np.asarray(train_x), label=np.asarray(train_y)),
        num_boost_round=40)
    return model


def fit_lightgbm(train_x, train_y, test_x):
    import numpy as np
    return train_lightgbm(train_x, train_y).predict(np.asarray(test_x), num_threads=2)


def evaluate(rows, fit_predict=None):
    train, test = prepare(rows)
    result = {"version": VERSION, "train_samples": len(train),
              "test_samples": len(test), "status": "INSUFFICIENT_EVIDENCE",
              "evidence_status": "EXPLORATORY_UNVERIFIED",
              "automatic_promotion": False, "live_prediction_verified": False,
              "profitability_verified": False, "real_orders": False}
    if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
        return result
    if fit_predict is None:
        fit_predict = fit_lightgbm
    # Holdout labels never enter the estimator.
    preds = list(fit_predict([r[2] for r in train], [r[3] for r in train],
                             [r[2] for r in test]))
    if len(preds) != len(test) or any(not math.isfinite(float(p)) or float(p) <= -100 for p in preds):
        raise ValueError("invalid holdout predictions")
    result["paired_mae_pct"] = {
        **{n: mean(r[4][n] for r in test) for n in MODELS},
        "lightgbm": mean(abs(r[3]-float(p)) for r,p in zip(test,preds))}
    result["status"] = "RESEARCH_MEASURED"
    return result


def run(root):
    if os.environ.get("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED") != "1":
        raise RuntimeError("research data rights confirmation required")
    from .journal_capacity import require_capacity
    require_capacity(root, 'LightGBM')
    import lightgbm as lgb
    folder = root/"var/ai"
    output = folder/"lightgbm-review-journal.sqlite3"
    if output.is_symlink() or (output.exists() and output.stat().st_nlink != 1):
        raise ValueError("unsafe output path")
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
        """, (MAX_ROWS,)).fetchall()
    key = hashlib.sha256(json.dumps([VERSION,lgb.__version__,rows],
                         separators=(",", ":"),allow_nan=False).encode()).hexdigest()
    with closing(sqlite3.connect(output,timeout=10)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS training_reports (
            fingerprint TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
        )""")
        cached = db.execute("SELECT payload FROM training_reports WHERE fingerprint=?",(key,)).fetchone()
        if cached:
            return {**json.loads(cached[0]),"cached":True}
        result = evaluate(rows)
        result.update(market="FUTURES",symbol="BTCUSDT",source="binance-usdm-public",
                      interval="1m",lightgbm_version=lgb.__version__,
                      created_at=datetime.now(timezone.utc).isoformat(),cached=False)
        if rows:
            require_capacity(root, 'LightGBM')
            db.execute("INSERT INTO training_reports VALUES (?,?,?)",
                       (key,result["created_at"],json.dumps(result,allow_nan=False)))
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("journal integrity failed")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.root.resolve()),indent=2,allow_nan=False))


if __name__ == "__main__":
    main()
