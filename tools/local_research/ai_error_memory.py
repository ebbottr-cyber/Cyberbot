"""Bounded read-only failure diagnostics from the existing forecast memory.

Categories overlap and are observations, not causal explanations. Never
update model weights, delete history or change trading policy.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

from .adaptive_review import MODELS, finite, readonly, utc, validated
from .ai_regime_review import VERSION as REGIME_VERSION, classify
from .journal_capacity import safe_stat

MAX_ROWS=10000
DEADBAND=.01
LARGE_ERROR=.25
MIN_SAMPLES=30
MIN_DAYS=5
REASONS={"missing_target_sample","target_not_after_forecast"}


def sign(value):
    return 1 if value>DEADBAND else -1 if value<-DEADBAND else 0


def regime(payload):
    if "regime_context" not in payload:
        return "unknown"
    r=payload["regime_context"]
    if r["version"]!=REGIME_VERSION or r["observations"]!=21:
        raise ValueError("invalid regime metadata")
    direction,volatility=classify(r["trend_log_pct"],r["volatility_log_pct"])
    if (direction,volatility)!=(r["direction"],r["volatility"]):
        raise ValueError("inconsistent regime")
    return direction+"/"+volatility


def bucket():
    return {"samples":0,"days":set(),"models":{n:Counter() for n in MODELS},
            "intervals":Counter()}


def summarize(rows):
    groups=defaultdict(bucket)
    measured=0
    unmeasurable=Counter()
    rejected=0
    previous=None
    for target,created,payload,status,outcome in rows:
        try:
            stamp=utc(created)
            if (type(target) is not int or target!=int(stamp.timestamp()//60)
                    or stamp.second>35 or stamp>datetime.now(timezone.utc)
                    or (previous is not None and target<=previous)):
                raise ValueError("invalid target chronology")
            previous=target
            p=json.loads(payload)
            o=json.loads(outcome)
            if status=="unmeasurable":
                if (p["mode"]!="forward_shadow_research" or p["real_orders"] is not False
                        or p["automatic_promotion"] is not False or o["reason"] not in REASONS):
                    raise ValueError("invalid unmeasurable outcome")
                unmeasurable[o["reason"]]+=1
                continue
            if status!="measured":
                raise ValueError("unexpected status")
            _,day,errors=validated((target,created,payload,outcome))
            actual=o["actual_return_pct"]
            if any(v>1e6 for v in errors.values()):
                raise ValueError("outlier")
            name=regime(p)
            pred=p["predictions"]
            lo,mid,hi,last=(p[k] for k in ("p10","p50","p90","last_price"))
            covered=o["interval_covered"]
            if (not all(finite(v) for v in (lo,mid,hi,last))
                    or not 0<lo<=mid<=hi or last<=0 or type(covered) is not bool
                    or not math.isclose((mid/last-1)*100,pred["chronos"],rel_tol=1e-9,abs_tol=1e-9)):
                raise ValueError("invalid interval")
            observed=last*(1+actual/100)
            if not finite(observed) or observed<=0:
                raise ValueError("invalid observed price")
            inside=lo<=observed<=hi
            boundary=math.isclose(observed,lo,rel_tol=1e-12) or math.isclose(observed,hi,rel_tol=1e-12)
            if inside!=covered and not boundary:
                raise ValueError("inconsistent coverage")
            interval="covered" if covered else "boundary_uncertain" if boundary else "below_p10" if observed<lo else "above_p90"
            flags={}
            for n in MODELS:
                v=pred[n]
                flags[n]={"opposite_direction":sign(v)*sign(actual)==-1,
                          "missed_movement":sign(v)==0 and sign(actual)!=0,
                          "false_movement":sign(v)!=0 and sign(actual)==0,
                          "large_absolute_error":errors[n]>=LARGE_ERROR,
                          "worse_than_zero_return":errors[n]>errors["naive"]+1e-9,
                          "overprediction":v-actual>DEADBAND,
                          "underprediction":actual-v>DEADBAND}
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError,ZeroDivisionError):
            rejected+=1
            continue
        measured+=1
        for key in ("all",name):
            group=groups[key]
            group["samples"]+=1
            group["days"].add(day)
            group["intervals"][interval]+=1
            for n in MODELS:
                for flag,value in flags[n].items():
                    group["models"][n][flag]+=int(value)
    base={"version":"ai-error-memory-1","scope":"FUTURES/BTCUSDT/binance-usdm-public",
          "window":"latest_finalized_records","row_limit":MAX_ROWS,"measured_records":measured,
          "unmeasurable_records":dict(unmeasurable),"rejected_records":rejected,
          "direction_deadband_pct":DEADBAND,"large_error_threshold_pct":LARGE_ERROR,
          "categories_can_overlap":True,"independent_samples":False,
          "causal_explanations_verified":False,"model_weights_updated":False,
          "automatic_promotion":False,"real_orders":False}
    if rejected:
        return {**base,"status":"DATA_REVIEW_REQUIRED","groups":[]}
    result=[]
    for name,g in sorted(groups.items()):
        n=g["samples"]
        result.append({"regime":name,"samples":n,"utc_days":len(g["days"]),
                       "status":"DESCRIPTIVE_ONLY" if n>=MIN_SAMPLES and len(g["days"])>=MIN_DAYS
                           else "LOW_SAMPLE",
                       "models":{model:{"counts":dict(counts),
                           "rates_pct":{k:100*v/n for k,v in counts.items()}}
                           for model,counts in g["models"].items()},
                       "chronos_interval_counts":dict(g["intervals"])})
    return {**base,"status":"RESEARCH_MEASURED" if measured else "INSUFFICIENT_EVIDENCE","groups":result}


def run(root):
    path=Path(root)/"var/ai/forward-models-v2.sqlite3"
    try:
        for p in (path.parent.parent,path.parent,path):
            if safe_stat(p) is None:
                return {**summarize([]),"status":"NOT_AVAILABLE"}
        if not path.is_file() or path.stat().st_nlink!=1:
            raise ValueError("unsafe journal")
        with closing(readonly(path)) as db:
            rows=db.execute("""SELECT target_minute,created_at,payload,status,outcome FROM (
                SELECT target_minute,created_at,payload,status,outcome FROM forecasts
                WHERE market='FUTURES' AND symbol='BTCUSDT' AND source='binance-usdm-public'
                AND status IN ('measured','unmeasurable')
                ORDER BY target_minute DESC LIMIT ?) ORDER BY target_minute""",(MAX_ROWS,)).fetchall()
        return summarize(rows)
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,OverflowError):
        return {**summarize([]),"status":"DATA_REVIEW_REQUIRED"}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    print(json.dumps(run(p.parse_args().root),indent=2,allow_nan=False))
