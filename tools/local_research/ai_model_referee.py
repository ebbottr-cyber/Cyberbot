"""Advisory model referee over one paired retrospective holdout report.

Never select a production model. No order, strategy, or model-state changes.
A better historical MAE is a candidate for further prospective testing only.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

from .adaptive_review import readonly, utc
from .journal_capacity import safe_stat

BASELINES=("naive","mean","ar1")
CANDIDATES=("chronos","lightgbm","river")
NAMES=(*BASELINES,*CANDIDATES)
MIN_TRAIN=100
MIN_TEST=60
MIN_DAYS=5
MAX_AGE_DAYS=7
MIN_GAIN=.05
MIN_MARGIN=.02


def assess(report, *, now=None, degradation_status=None):
    now=now or datetime.now(timezone.utc)
    base={"version":"ai-model-referee-1","scope":"FUTURES/BTCUSDT/binance-usdm-public",
          "status":"INSUFFICIENT_EVIDENCE","review_candidate":None,
          "active_model_changed":False,"automatic_promotion":False,
          "prospective_validation_required":True,"profitability_verified":False,
          "real_orders":False,
          "policy":{"min_train":MIN_TRAIN,"min_test":MIN_TEST,"min_holdout_days":MIN_DAYS,
                    "max_target_age_days":MAX_AGE_DAYS,"min_gain_vs_best_baseline":MIN_GAIN,
                    "min_margin_vs_next_candidate":MIN_MARGIN}}
    if report is None:
        return base
    try:
        if (report["version"]!="paired-ai-review-1"
                or report["comparison_protocol"]!="same_targets_frozen_batch_online_replay"
                or report["evidence_status"]!="EXPLORATORY_UNVERIFIED"
                or (report["market"],report["symbol"],report["source"],report["interval"])!=
                    ("FUTURES","BTCUSDT","binance-usdm-public","1m")
                or any(report[k] is not False for k in ("live_prediction_verified",
                    "automatic_promotion","profitability_verified","real_orders"))):
            raise ValueError("invalid comparison scope")
        if report["status"]=="INSUFFICIENT_EVIDENCE":
            return base
        if report["status"]!="RESEARCH_MEASURED":
            raise ValueError("invalid report status")
        train,test,days=(report[k] for k in ("train_samples","test_samples","holdout_days"))
        first,last=(report[k] for k in ("first_target_minute","last_target_minute"))
        if any(type(v) is not int or v<1 for v in (train,test,days,first,last)):
            raise ValueError("invalid sample metadata")
        start,end=(datetime.fromtimestamp(v*60,timezone.utc) for v in (first,last))
        created=utc(report["created_at"])
        if (first>last or end>created or created>now or days>(end.date()-start.date()).days+1
                or days>test or train+test>10000 or (test-1)*22>last-first):
            raise ValueError("invalid holdout chronology")
        scores=report["daily_weighted_mae_pct"]
        if set(scores)!=set(NAMES) or any(type(v) not in (int,float) or
                not math.isfinite(v) or not 0<=v<=1e6 for v in scores.values()):
            raise ValueError("invalid paired scores")
        result={**base,"train_samples":train,"test_samples":test,"holdout_days":days,
                "last_target_utc":end.isoformat(),"report_created_at_utc":created.isoformat(),
                "daily_weighted_mae_pct":scores,
                "comparison_protocol":"same_targets_frozen_batch_online_replay",
                "retrospective_comparison_only":True}
        if (now-end).total_seconds()>MAX_AGE_DAYS*86400:
            return {**result,"status":"STALE_EVIDENCE"}
        if train<MIN_TRAIN or test<MIN_TEST or days<MIN_DAYS:
            return result
        if degradation_status=="REVIEW_DEGRADATION":
            return {**result,"status":"DEPENDENCY_REVIEW_REQUIRED"}
        baseline=min(BASELINES,key=lambda n:scores[n])
        ranked=sorted(CANDIDATES,key=lambda n:scores[n])
        best,runner=ranked[:2]
        b,r=scores[baseline],scores[runner]
        result.update(best_reference=baseline)
        if b<=0 or scores[best]>b*(1-MIN_GAIN):
            return {**result,"status":"NO_BASELINE_ADVANTAGE"}
        if r<=0 or scores[best]>r*(1-MIN_MARGIN):
            return {**result,"status":"NO_CLEAR_LEADER"}
        return {**result,"status":"REVIEW_ONLY","review_candidate":best,
                "relative_gain_vs_reference_pct":100*(1-scores[best]/b)}
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,OSError):
        return {**base,"status":"DATA_REVIEW_REQUIRED"}


def run(root, *, degradation_status=None):
    path=Path(root)/"var/ai/paired-ai-review.sqlite3"
    try:
        for p in (path.parent.parent,path.parent,path):
            if safe_stat(p) is None:
                return {**assess(None),"status":"NOT_AVAILABLE"}
        if not path.is_file() or path.stat().st_nlink!=1:
            raise ValueError("unsafe journal")
        with closing(readonly(path)) as db:
            row=db.execute("""SELECT payload FROM paired_reports
                ORDER BY created_at DESC,fingerprint DESC LIMIT 1""").fetchone()
        return assess(json.loads(row[0]) if row else None,
                      degradation_status=degradation_status)
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,OverflowError):
        return {**assess(None),"status":"DATA_REVIEW_REQUIRED"}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    args=p.parse_args()
    from .ai_performance_history import run as forward_history
    from .ai_review_history import degradation
    flag=degradation(forward_history(args.root))["status"]
    print(json.dumps(run(args.root,degradation_status=flag),indent=2,allow_nan=False))
