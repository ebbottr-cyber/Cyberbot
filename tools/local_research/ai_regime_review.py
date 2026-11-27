"""Causal instrument regime research; never a strategy or trade gate."""
import argparse
from collections import defaultdict
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
from statistics import mean, pstdev

from .adaptive_review import MODELS, finite, readonly, validated
from .journal_capacity import safe_stat

VERSION="forward-regime-1"
TREND=.5
VOL=.2
MAX_ROWS=10000
SPACING=22


def classify(trend,vol):
    if not finite(trend) or not finite(vol) or vol<0:
        raise ValueError("invalid regime statistics")
    return ("bull" if trend>=TREND else "bear" if trend<=-TREND else "sideways",
            "high" if vol>=VOL else "normal")


def context(prices):
    # Same provisional thresholds as observed_regime, without book assumptions.
    if len(prices)!=21 or any(not finite(p) or p<=0 for p in prices):
        raise ValueError("invalid price context")
    moves=[100*(math.log(b)-math.log(a)) for a,b in zip(prices,prices[1:])]
    trend,vol=sum(moves),pstdev(moves)
    direction,volatility=classify(trend,vol)
    return {"version":VERSION,"observations":21,"trend_log_pct":trend,
            "volatility_log_pct":vol,"direction":direction,"volatility":volatility}


def summarize(rows):
    groups=defaultdict(lambda:defaultdict(list))
    missing=rejected=retained=0
    previous=last_kept=None
    for row in rows:
        try:
            target,day,errors=validated(row)
            if previous is not None and target<=previous:
                raise ValueError("duplicate or unordered target")
            previous=target
            p=json.loads(row[2])
            if "regime_context" not in p:
                missing+=1
                continue
            r=p["regime_context"]
            if r["version"]!=VERSION or r["observations"]!=21:
                raise ValueError("unexpected regime context")
            direction,volatility=classify(r["trend_log_pct"],r["volatility_log_pct"])
            if (direction,volatility)!=(r["direction"],r["volatility"]):
                raise ValueError("inconsistent regime label")
            if any(v>1e6 for v in errors.values()):
                raise ValueError("outlier")
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
            rejected+=1
            continue
        if last_kept is not None and target-last_kept<SPACING:
            continue
        last_kept=target
        retained+=1
        groups[(direction,volatility)][day].append(errors)
    base={"version":VERSION,"scope":"FUTURES/BTCUSDT/binance-usdm-public",
          "thresholds":{"trend_log_pct":TREND,"volatility_per_minute_log_pct":VOL},
          "spacing_minutes":SPACING,"retained_blocks":retained,
          "missing_regime_metadata":missing,"rejected_records":rejected,
          "metadata_independently_recomputed":False,"calibrated":False,
          "automatic_strategy_switching":False,"profitability_verified":False,
          "real_orders":False}
    if rejected:
        return {**base,"status":"DATA_REVIEW_REQUIRED","regimes":[]}
    output=[]
    for direction in ("bull","bear","sideways"):
        for volatility in ("normal","high"):
            days=groups[(direction,volatility)]
            n=sum(len(v) for v in days.values())
            metrics={name:mean(mean(x[name] for x in v) for v in days.values())
                     for name in MODELS} if n else {}
            output.append({"direction":direction,"volatility":volatility,
                           "blocks":n,"utc_days":len(days),
                           "daily_weighted_mae_pct":metrics,
                           "status":"DESCRIPTIVE_ONLY" if n>=30 and len(days)>=5
                           else "INSUFFICIENT_EVIDENCE"})
    return {**base,"status":"RESEARCH_MEASURED" if retained else "INSUFFICIENT_EVIDENCE",
            "regimes":output}


def run(root):
    path=Path(root)/"var/ai/forward-models-v2.sqlite3"
    try:
        for p in (path.parent.parent,path.parent,path):
            if safe_stat(p) is None:
                return {**summarize([]),"status":"NOT_AVAILABLE"}
        if not path.is_file() or path.stat().st_nlink!=1:
            raise ValueError("unsafe journal")
        with closing(readonly(path)) as db:
            rows=db.execute("""SELECT target_minute,created_at,payload,outcome FROM (
                SELECT target_minute,created_at,payload,outcome FROM forecasts
                WHERE market='FUTURES' AND symbol='BTCUSDT'
                AND source='binance-usdm-public' AND status='measured'
                ORDER BY target_minute DESC LIMIT ?) ORDER BY target_minute""",
                (MAX_ROWS,)).fetchall()
        return summarize(rows)
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,OverflowError):
        return {**summarize([]),"status":"DATA_REVIEW_REQUIRED","regimes":[]}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    print(json.dumps(run(p.parse_args().root),indent=2,allow_nan=False))
