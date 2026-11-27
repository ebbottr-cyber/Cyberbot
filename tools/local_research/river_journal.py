"""Bounded, repeatable River replay from settled Futures forecasts.

This is a retrospective audit, not a live River forecast or trading signal.
Reconstruct state from data rather than loading executable pickle files.
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
from statistics import mean

from .adaptive_review import validated, readonly, MODELS

VERSION = "river-forward-replay-1"
MAX_ROWS = 10000
WARMUP = 60


def replay(rows, model):
    errors = {n: [] for n in (*MODELS, "river")}
    digest = hashlib.sha256()
    previous = None
    count = 0
    for row in rows:
        target, _, paired = validated(row)
        if previous is not None and target <= previous:
            raise ValueError("duplicate or unordered observation")
        previous = target
        p, o = json.loads(row[2]), json.loads(row[3])
        # All features existed in the original forecast payload.
        x = {n: p["predictions"][n] for n in MODELS if n != "naive"}
        y = o["actual_return_pct"]
        pred = model.predict_one(x)
        if not isinstance(pred, (int, float)) or not math.isfinite(pred) or pred <= -100:
            raise ValueError("invalid replay prediction")
        if count >= WARMUP:
            for name in MODELS:
                errors[name].append(paired[name])
            errors["river"].append(abs(y-pred))
        model.learn_one(x, y)
        count += 1
        digest.update(json.dumps(row, separators=(",", ":"), allow_nan=False).encode())
        digest.update(b"\n")
    scored = max(0, count-WARMUP)
    return {"version": VERSION, "source_fingerprint": digest.hexdigest(),
            "observations": count, "scored": scored, "last_target": previous,
            "paired_mae_pct": {n: mean(v) for n, v in errors.items()} if scored else {},
            "evidence_status": "EXPLORATORY_UNVERIFIED",
            "live_prediction_verified": False, "automatic_promotion": False,
            "profitability_verified": False, "real_orders": False}


def run(root):
    if os.environ.get("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED") != "1":
        raise RuntimeError("local research data rights confirmation required")
    from .journal_capacity import require_capacity
    require_capacity(root, 'RiverReplay')
    from river import linear_model, preprocessing, __version__ as river_version
    from .vps_guard import MIN_FREE_DISK_MIB, MIB
    import shutil
    folder = root/"var/ai"
    source = folder/"forward-models-v2.sqlite3"
    output = folder/"river-replay-journal.sqlite3"
    if output.is_symlink() or (output.exists() and output.stat().st_nlink != 1):
        raise ValueError("unsafe journal path")
    if shutil.disk_usage(folder).free//MIB < MIN_FREE_DISK_MIB:
        raise RuntimeError("insufficient disk")
    with closing(readonly(source)) as conn:
        rows = conn.execute("""
            SELECT target_minute,created_at,payload,outcome FROM (
                SELECT target_minute,created_at,payload,outcome FROM forecasts
                WHERE market='FUTURES' AND symbol='BTCUSDT'
                AND source='binance-usdm-public' AND status='measured'
                ORDER BY target_minute DESC LIMIT ?
            ) ORDER BY target_minute
        """, (MAX_ROWS,))
        model = preprocessing.StandardScaler() | linear_model.LinearRegression()
        result = replay(rows, model)
    result["river_version"] = river_version
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    result["market"] = "FUTURES"
    result["symbol"] = "BTCUSDT"
    result["window_limit"] = MAX_ROWS
    key = hashlib.sha256(json.dumps([VERSION,river_version,result["source_fingerprint"]]).encode()).hexdigest()
    # Only aggregate summaries are persisted; no raw feature/target pairs or model pickle.
    require_capacity(root, 'RiverReplay')
    with closing(sqlite3.connect(output,timeout=10)) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS replay_reports (
            fingerprint TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
        )""")
        if result["observations"]:
            conn.execute("INSERT OR IGNORE INTO replay_reports VALUES (?,?,?)",
                         (key,result["created_at"],json.dumps(result,allow_nan=False)))
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("journal integrity failed")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    args = p.parse_args()
    print(json.dumps(run(args.root.resolve()),indent=2,allow_nan=False))


if __name__ == "__main__":
    main()
