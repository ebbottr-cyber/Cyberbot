"""Read-only learning review planner; never starts training or changes models.

Use a paired comparison target watermark, not the report generation time,
to count new observations. Recommendations are not scheduler instructions.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from .adaptive_review import utc, readonly
from .lightgbm_journal import prepare, MAX_ROWS
from .journal_capacity import safe_stat
from .ai_model_referee import MIN_TRAIN, MIN_TEST, MIN_DAYS

MIN_NEW_BLOCKS=30
MIN_NEW_DAYS=2
COOLDOWN_SECONDS=86400
SCOPE="FUTURES/BTCUSDT/binance-usdm-public"


def plan(snapshot,train,test,*,now=None):
    now=now or datetime.now(timezone.utc)
    base={"version":"ai-learning-cycle-1","scope":SCOPE,"status":"WAIT_EVIDENCE",
          "reasons":[],"train_samples":len(train),"test_samples":len(test),
          "holdout_days":len({r[1] for r in test}),
          "min_new_blocks":MIN_NEW_BLOCKS,"min_new_days":MIN_NEW_DAYS,
          "cooldown_seconds":COOLDOWN_SECONDS,
          "chronos_weights_updated":False,"training_started":False,
          "automatic_promotion":False,"real_orders":False}
    try:
        errors=snapshot["error_memory"]
        history=snapshot["forward_performance_history"]
        referee=snapshot["model_referee"]
        drift=snapshot["model_review_history"]["chronos_degradation"]
        storage=snapshot["journal_capacity"]
        if (snapshot["real_orders"] is not False or snapshot["automatic_promotion"] is not False
                or any(x.get("scope")!=SCOPE for x in (errors,history,referee))
                or any(x.get("status")=="DATA_REVIEW_REQUIRED" for x in (errors,history,referee,storage))):
            return {**base,"status":"DATA_REVIEW_REQUIRED"}
        if storage["status"]!="BELOW_LIMIT":
            return {**base,"status":"WAIT_STORAGE"}
        if errors["status"]!="RESEARCH_MEASURED" or history["status"]!="RESEARCH_MEASURED":
            return base
        measured=errors["measured_records"]
        missing=sum(errors["unmeasurable_records"].values())
        if (type(measured) is not int or measured<=0 or missing<0
                or errors["rejected_records"]!=0 or history["rejected_records"]!=0):
            return {**base,"status":"DATA_REVIEW_REQUIRED"}
        if missing/(measured+missing)>.1:
            return {**base,"status":"DATA_REVIEW_REQUIRED","reasons":["HIGH_UNMEASURABLE_SHARE"]}
        if len(train)<MIN_TRAIN or len(test)<MIN_TEST or base["holdout_days"]<MIN_DAYS:
            return base
        reasons=[]
        if drift["status"]=="REVIEW_DEGRADATION":
            reasons.append("CHRONOS_DEGRADATION_REVIEW")
        overall=next((g for g in errors["groups"] if g["regime"]=="all"),None)
        if overall and overall["status"]=="DESCRIPTIVE_ONLY":
            rate=overall["models"]["chronos"]["rates_pct"]["worse_than_zero_return"]
            if type(rate) not in (int,float) or not 0<=rate<=100:
                raise ValueError("invalid diagnostic rate")
            if rate>=40:
                reasons.append("CHRONOS_REFERENCE_ERROR_REVIEW")
        last=referee.get("last_target_utc")
        if last is None:
            if referee["status"] not in ("NOT_AVAILABLE","INSUFFICIENT_EVIDENCE"):
                return {**base,"status":"DATA_REVIEW_REQUIRED"}
            return {**base,"status":"INITIAL_COMPARISON_REVIEW",
                    "reasons":["NO_MEASURED_PAIRED_BASELINE",*reasons],
                    "next_review":"PAIRED_LIGHTGBM_RIVER_RESEARCH"}
        watermark=utc(last)
        created=utc(referee["report_created_at_utc"])
        if not watermark<=created<=now:
            raise ValueError("invalid comparison timing")
        new=[r for r in train+test if r[0]*60>watermark.timestamp()]
        base.update(new_retained_blocks=len(new),new_utc_days=len({r[1] for r in new}),
                    previous_target_utc=watermark.isoformat())
        if len(new)<MIN_NEW_BLOCKS or base["new_utc_days"]<MIN_NEW_DAYS:
            return {**base,"status":"WAIT_NEW_DATA","reasons":reasons}
        if (now-created).total_seconds()<COOLDOWN_SECONDS:
            return {**base,"status":"WAIT_COOLDOWN","reasons":reasons}
        reasons.append("NEW_CHRONOLOGICAL_EVIDENCE")
        return {**base,"status":"RECOMPARISON_REVIEW","reasons":reasons,
                "next_review":"PAIRED_LIGHTGBM_RIVER_RESEARCH"}
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
        return {**base,"status":"DATA_REVIEW_REQUIRED"}


def run(root,snapshot):
    path=Path(root)/"var/ai/forward-models-v2.sqlite3"
    try:
        for item in (path.parent.parent,path.parent,path):
            if safe_stat(item) is None:
                return plan(snapshot,[],[])
        if not path.is_file() or path.stat().st_nlink!=1:
            raise ValueError("unsafe journal")
        with closing(readonly(path)) as db:
            rows=db.execute("""SELECT target_minute,created_at,payload,outcome FROM (
                SELECT target_minute,created_at,payload,outcome FROM forecasts
                WHERE market='FUTURES' AND symbol='BTCUSDT'
                AND source='binance-usdm-public' AND status='measured'
                ORDER BY target_minute DESC LIMIT ?) ORDER BY target_minute""",(MAX_ROWS,)).fetchall()
        train,test=prepare(rows)
        return plan(snapshot,train,test)
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,OverflowError):
        return {**plan(snapshot,[],[]),"status":"DATA_REVIEW_REQUIRED"}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    args=p.parse_args()
    from .ai_dashboard import snapshot
    print(json.dumps(snapshot(args.root)["learning_cycle"],indent=2,allow_nan=False))
