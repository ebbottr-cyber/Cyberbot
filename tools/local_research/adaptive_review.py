"""Conservative, offline model review; never changes strategy or model weights."""
import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from statistics import mean

MODELS = ("naive", "mean", "ar1", "chronos")
MIN_BLOCKS = 60
MIN_DAYS = 10
MIN_GAIN = 0.05
CONTEXT = 21


def finite(x):
    return type(x) in (float, int) and math.isfinite(x)


def utc(value):
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("timezone missing")
    return t.astimezone(timezone.utc)


def validated(row):
    minute, created, payload, outcome = row
    p, o = json.loads(payload), json.loads(outcome)
    start, end = utc(created), utc(o["target_source_at"])
    if (type(minute) is not int or int(start.timestamp() // 60) != minute
            or int(end.timestamp() // 60) != minute
            or start.second > 35 or end <= start or end.second < 45
            or end > datetime.now(timezone.utc)):
        raise ValueError("invalid forward timing")
    if (p["mode"] != "forward_shadow_research"
            or p["context_bars"] != CONTEXT or p["prediction_bars"] != 1
            or p["automatic_promotion"] is not False or p["real_orders"] is not False
            or o["execution_verified"] is not False or o["real_orders"] is not False):
        raise ValueError("invalid evidence mode")
    pred, errors = p["predictions"], o["absolute_errors_pct"]
    actual = o["actual_return_pct"]
    if set(pred) != set(MODELS) or set(errors) != set(MODELS) or not finite(actual):
        raise ValueError("invalid paired model data")
    if not finite(p["last_price"]) or p["last_price"] <= 0 or actual <= -100:
        raise ValueError("invalid price")
    if pred["naive"] != 0:
        raise ValueError("invalid baseline")
    for name in MODELS:
        if not finite(pred[name]) or not finite(errors[name]) or errors[name] < 0:
            raise ValueError("invalid error")
        if not math.isclose(errors[name], abs(actual-pred[name]), rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("error mismatch")
    return minute, end.date().isoformat(), errors


def review(rows):
    """One retained window per 22 minutes, split by whole UTC days.
    Evidence remains observational; thresholds are not a significance test.
    """
    kept, rejected = [], 0
    last_seen = last_kept = None
    for row in rows:
        try:
            item = validated(row)
            if last_seen is not None and item[0] <= last_seen:
                raise ValueError("unordered or duplicate target")
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            rejected += 1
            continue
        last_seen = item[0]
        if last_kept is None or item[0]-last_kept >= CONTEXT+1:
            kept.append(item)
            last_kept = item[0]
    days = sorted({x[1] for x in kept})
    result = {"retained_blocks": len(kept), "days": len(days),
              "rejected_records": rejected, "status": "INSUFFICIENT_EVIDENCE",
              "review_candidate": None, "automatic_model_selection": False}
    if len(kept) < MIN_BLOCKS or len(days) < MIN_DAYS:
        return result
    if rejected:
        result["status"] = "DATA_REVIEW_REQUIRED"
        return result
    holdout_days = set(days[len(days)*2//3:])
    train = [x for x in kept if x[1] not in holdout_days]
    holdout = [x for x in kept if x[1] in holdout_days]
    if len(train) < 40 or len(holdout) < 20:
        return result
    def scores(items):
        # Equal UTC-day weights reduce dominance of high-frequency days.
        by_day = defaultdict(list)
        for _, day, errors in items:
            by_day[day].append(errors)
        return {n: mean(mean(e[n] for e in group) for group in by_day.values())
                for n in MODELS}
    a, b = scores(train), scores(holdout)
    candidate = min(MODELS, key=lambda n: a[n])
    def improved(scores):
        return scores["naive"] > 0 and scores[candidate] <= scores["naive"]*(1-MIN_GAIN)
    result.update({"development_blocks": len(train), "holdout_blocks": len(holdout),
                   "development_mae_pct": a, "holdout_mae_pct": b,
                   "status": "NO_CANDIDATE"})
    if candidate != "naive" and improved(a) and improved(b):
        result.update(status="REVIEW_ONLY", review_candidate=candidate)
    return result


def readonly(path):
    path = Path(path).resolve(strict=True)
    conn = sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def run(root):
    with closing(readonly(root/"var/learning.sqlite3")) as db:
        # Never pool overlapping historical reports as independent evidence.
        history = [dict(zip(("source_group", "kind", "reports"), row)) for row in db.execute("""
            SELECT source_group,kind,COUNT(*) FROM equity5m_research_reports
            WHERE evidence_status='EXPLORATORY_UNVERIFIED'
            GROUP BY source_group,kind ORDER BY source_group,kind
        """)]
    with closing(readonly(root/"var/ai/forward-models-v2.sqlite3")) as db:
        counts = dict(db.execute("""
            SELECT status,COUNT(*) FROM forecasts
            WHERE market='FUTURES' AND symbol='BTCUSDT' AND source='binance-usdm-public'
            GROUP BY status
        """))
        rows = db.execute("""
            SELECT target_minute,created_at,payload,outcome FROM forecasts
            WHERE market='FUTURES' AND symbol='BTCUSDT' AND source='binance-usdm-public'
            AND status='measured' ORDER BY target_minute
        """)
        forward = review(rows)
    return {"version": "adaptive-review-1", "historical_report_inventory": history,
            "historical_evidence": "EXPLORATORY_UNVERIFIED",
            "futures": {"market": "FUTURES", "symbol": "BTCUSDT", "source": "binance-usdm-public",
                        "interval": "1m", "counts": counts, **forward},
            "equities": {m: {i: "FORWARD_EVIDENCE_REQUIRED" for i in ("5m","1d")}
                         for m in ("BIST","NASDAQ","XETRA")},
            "solana": "FORWARD_EVIDENCE_REQUIRED",
            "policy": {"min_blocks": MIN_BLOCKS, "min_days": MIN_DAYS,
                       "min_relative_mae_gain": MIN_GAIN, "min_spacing_minutes": CONTEXT+1},
            "independent_validation": False, "license_verified": False,
            "automatic_promotion": False, "model_weights_updated": False,
            "profitability_verified": False, "real_orders": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.root.resolve()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
