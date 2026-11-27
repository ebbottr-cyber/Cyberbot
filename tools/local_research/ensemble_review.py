"""Offline chronological ensemble experiment; no trading or model activation."""
import argparse
from collections import defaultdict
from contextlib import closing
import json
import math
import os
from pathlib import Path
from statistics import mean

from .adaptive_review import MODELS, readonly
from .lightgbm_journal import FEATURES, MAX_ROWS, prepare, fit_lightgbm
from .paired_ai_review import make_river, predict_value
from .journal_capacity import safe_stat
from .ai_regime_review import classify, VERSION as REGIME_VERSION

NAMES=("chronos","lightgbm","river")
# All candidates keep all three members. The equal blend is also eligible.
WEIGHTS=((1/3,1/3,1/3),)+tuple((a/10,b/10,(10-a-b)/10)
    for a in range(2,7) for b in range(2,7) if 2<=10-a-b<=6)


def score(records, weights):
    days=defaultdict(list)
    for day,actual,predictions,_ in records:
        error=abs(actual-sum(w*p for w,p in zip(weights,predictions)))
        if not math.isfinite(error):
            raise ValueError("nonfinite blend error")
        days[day].append(error)
    return mean(mean(v) for v in days.values())


def regime_key(payload):
    p=json.loads(payload)
    if "regime_context" not in p:
        return None
    r=p["regime_context"]
    if r["version"]!=REGIME_VERSION or r["observations"]!=21:
        raise ValueError("invalid regime metadata")
    direction,volatility=classify(r["trend_log_pct"],r["volatility_log_pct"])
    if (direction,volatility)!=(r["direction"],r["volatility"]):
        raise ValueError("inconsistent regime metadata")
    return direction+"/"+volatility


def choose_regime_weights(records, keys, global_weights):
    if len(records)!=len(keys):
        raise ValueError("regime alignment mismatch")
    groups=defaultdict(list)
    for record,key in zip(records,keys):
        if key is not None:
            groups[key].append(record)
    policies={}
    for key,items in sorted(groups.items()):
        if len(items)<30 or len({x[0] for x in items})<5:
            continue
        baseline=score(items,global_weights)
        candidate=min(WEIGHTS,key=lambda w:score(items,w))
        # Keep the simpler global policy unless calibration improvement is material.
        if baseline>0 and score(items,candidate)<=.95*baseline:
            policies[key]=candidate
    return policies


def adaptive_score(records,keys,global_weights,policies):
    if len(records)!=len(keys):
        raise ValueError("regime alignment mismatch")
    days=defaultdict(list)
    usage=defaultdict(int)
    for (day,actual,predictions,_),key in zip(records,keys):
        weights=policies.get(key,global_weights)
        error=abs(actual-sum(w*p for w,p in zip(weights,predictions)))
        if not math.isfinite(error):
            raise ValueError("nonfinite adaptive error")
        days[day].append(error)
        usage[key if key in policies else "global_fallback"]+=1
    return mean(mean(v) for v in days.values()),dict(usage)


def compare(rows, *, batch_fit=fit_lightgbm, online_factory=make_river, adaptive=False):
    if adaptive:
        rows=list(rows)
        keys={r[0]:regime_key(r[2]) for r in rows}
    early,late=prepare(rows)
    kept=early+late
    dates=sorted({r[1] for r in kept})
    result={"version":"ensemble-review-1","status":"INSUFFICIENT_EVIDENCE",
            "scope":"FUTURES/BTCUSDT/binance-usdm-public",
            "protocol":"chronological_train_calibration_holdout",
            "live_prediction_verified":False,"automatic_promotion":False,
            "profitability_verified":False,"real_orders":False}
    if len(dates)<12:
        return result
    a,b=len(dates)//2,len(dates)*3//4
    fit_days,cal_days=set(dates[:a]),set(dates[a:b])
    train=[r for r in kept if r[1] in fit_days]
    calibration=[r for r in kept if r[1] in cal_days]
    test=[r for r in kept if r[1] not in fit_days|cal_days]
    result.update(train_samples=len(train),calibration_samples=len(calibration),
                  test_samples=len(test),train_days=a,calibration_days=b-a,
                  test_days=len(dates)-b)
    if len(train)<60 or len(calibration)<30 or len(test)<30:
        return result
    # Frozen batch model sees only the initial training labels.
    batch=list(batch_fit([r[2] for r in train],[r[3] for r in train],
                         [r[2] for r in calibration+test]))
    if len(batch)!=len(calibration)+len(test):
        raise ValueError("batch prediction count mismatch")
    online=online_factory()
    for r in train:
        online.learn_one(dict(zip(FEATURES,r[2])),r[3])

    def evaluate(items,predicted):
        records=[]
        for row,lgb in zip(items,predicted):
            _,day,values,y,base=row
            x=dict(zip(FEATURES,values))
            predictions=(predict_value(x["chronos"]),predict_value(lgb),
                         predict_value(online.predict_one(x)))
            errors={**base,"lightgbm":abs(y-predictions[1]),"river":abs(y-predictions[2])}
            if any(not math.isfinite(v) or not 0<=v<=1e6 for v in errors.values()):
                raise ValueError("invalid evaluation error")
            records.append((day,y,predictions,errors))
            # Predict before observing the completed target; 22-minute spacing.
            online.learn_one(x,y)
        return records

    cal=evaluate(calibration,batch[:len(calibration)])
    # No holdout result participates in this selection.
    weights=min(WEIGHTS,key=lambda w:score(cal,w))
    calibration_mae=score(cal,weights)
    if adaptive:
        policies=choose_regime_weights(cal,[keys[r[0]] for r in calibration],weights)
    holdout=evaluate(test,batch[len(calibration):])
    days=defaultdict(list)
    for day,_,_,errors in holdout:
        days[day].append(errors)
    scores={n:mean(mean(e[n] for e in group) for group in days.values())
            for n in (*MODELS,"lightgbm","river")}
    scores["ensemble"]=score(holdout,weights)
    scores["equal_blend"]=score(holdout,WEIGHTS[0])
    reference=min(scores[n] for n in scores if n!="ensemble")
    result.update(status="REVIEW_ONLY" if reference>0 and scores["ensemble"]<=.95*reference
                  else "NO_CLEAR_ADVANTAGE",
                  weights=dict(zip(NAMES,weights)),calibration_mae_pct=calibration_mae,
                  holdout_daily_weighted_mae_pct=scores,
                  first_holdout_day=test[0][1],last_holdout_day=test[-1][1],
                  gain_vs_best_reference_pct=100*(1-scores["ensemble"]/reference)
                  if reference>0 and math.isfinite(scores["ensemble"]/reference) else None,
                  weights_frozen_before_holdout=True,independent_validation=False)
    if adaptive:
        adaptive_mae,usage=adaptive_score(holdout,[keys[r[0]] for r in test],weights,policies)
        ref=min(reference,scores["ensemble"])
        result["adaptive_regime_review"]={
            "status":"REVIEW_ONLY" if policies and any(k!="global_fallback" for k in usage)
                and ref>0 and adaptive_mae<=.95*ref else "NO_CLEAR_ADVANTAGE",
            "regime_weights":{k:dict(zip(NAMES,v)) for k,v in policies.items()},
            "global_fallback_weights":dict(zip(NAMES,weights)),
            "holdout_usage":usage,"holdout_daily_weighted_mae_pct":adaptive_mae,
            "global_holdout_mae_pct":scores["ensemble"],
            "min_calibration_blocks_per_regime":30,"min_calibration_days_per_regime":5,
            "min_calibration_improvement":.05,
            "weights_frozen_before_holdout":True,
            "metadata_independently_recomputed":False,"automatic_promotion":False,
            "real_orders":False}
    return result


def run(root, *, adaptive=False):
    if os.getenv("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("local research rights confirmation required")
    path=Path(root)/"var/ai/forward-models-v2.sqlite3"
    for item in (path.parent.parent,path.parent,path):
        if safe_stat(item) is None:
            raise ValueError("local forward journal required")
    if not path.is_file() or path.stat().st_nlink!=1:
        raise ValueError("unsafe journal")
    with closing(readonly(path)) as db:
        rows=db.execute("""SELECT target_minute,created_at,payload,outcome FROM (
            SELECT target_minute,created_at,payload,outcome FROM forecasts
            WHERE market='FUTURES' AND symbol='BTCUSDT'
            AND source='binance-usdm-public' AND status='measured'
            ORDER BY target_minute DESC LIMIT ?) ORDER BY target_minute""",(MAX_ROWS,)).fetchall()
    return compare(rows,adaptive=adaptive)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--adaptive-regimes",action="store_true")
    args=p.parse_args()
    print(json.dumps(run(args.root.resolve(),adaptive=args.adaptive_regimes),indent=2,allow_nan=False))
