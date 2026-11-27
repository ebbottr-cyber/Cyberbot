"""Bounded daily prospective forecast diagnostics, not trading performance.

Each measured observation is revalidated. Equal target sets are used for
the four baseline/Chronos metrics. Overlapping contexts are not independent.
No persistence, model updates, or strategy promotion.
"""
import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from statistics import mean

from .adaptive_review import MODELS, validated, readonly
from .journal_capacity import safe_stat

MAX_ROWS = 10000
MAX_DAYS = 30
MIN_DAILY = 20


def summarize(rows, *, now=None):
    now=now or datetime.now(timezone.utc)
    groups=defaultdict(list)
    rejected=0
    previous=None
    for row in rows:
        try:
            target,day,errors=validated(row)
            if previous is not None and target<=previous:
                raise ValueError("unordered or duplicate target")
            if target*60>now.timestamp():
                raise ValueError("future observation")
            p,o=json.loads(row[2]),json.loads(row[3])
            actual=o["actual_return_pct"]
            predictions=p["predictions"]
            if any(abs(actual-v)>1e6 for v in predictions.values()):
                raise ValueError("outlier requires review")
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
            rejected+=1
            continue
        previous=target
        groups[day].append((errors,actual,predictions))
    if rejected:
        return {"status":"DATA_REVIEW_REQUIRED","rejected_records":rejected,"days":[]}
    result=[]
    for day in sorted(groups)[-MAX_DAYS:]:
        items=groups[day]
        n=len(items)
        scores={name:mean(x[0][name] for x in items) for name in MODELS}
        direction={name:sum((1 if pred[name]>0 else -1 if pred[name]<0 else 0)==
                            (1 if actual>0 else -1 if actual<0 else 0)
                            for _,actual,pred in items)/n*100 for name in MODELS}
        result.append({"day_utc":day,"measured_forecasts":n,
                       "mae_pct":scores,"direction_match_pct":direction,
                       "chronos_relative_mae_gain_pct":None if scores["naive"]==0 else
                       (1-scores["chronos"]/scores["naive"])*100,
                       "sample_status":"DESCRIPTIVE_ONLY" if n>=MIN_DAILY else "LOW_SAMPLE",
                       "day_complete":day<now.date().isoformat()})
    return {"status":"RESEARCH_MEASURED" if result else "INSUFFICIENT_EVIDENCE",
            "days":result,"rejected_records":0}


def run(root):
    base={"version":"ai-forward-history-1","scope":"FUTURES/BTCUSDT/binance-usdm-public",
          "interval":"1m","protocol":"prospective_shadow_same_targets",
          "window":"latest_measured_rows","row_limit":MAX_ROWS,"day_limit":MAX_DAYS,
          "independent_samples":False,"direction_match_is_trade_win_rate":False,
          "automatic_promotion":False,"profitability_verified":False,"real_orders":False}
    root=Path(root)
    path=root/"var/ai/forward-models-v2.sqlite3"
    try:
        for part in (path.parent.parent,path.parent,path):
            if safe_stat(part) is None:
                return {**base,"status":"NOT_AVAILABLE","days":[]}
        if not path.is_file() or path.stat().st_nlink!=1:
            raise ValueError("unsafe journal")
        with closing(readonly(path)) as db:
            db.execute("BEGIN")
            rows=db.execute("""SELECT target_minute,created_at,payload,outcome FROM (
                SELECT target_minute,created_at,payload,outcome FROM forecasts
                WHERE market='FUTURES' AND symbol='BTCUSDT'
                AND source='binance-usdm-public' AND status='measured'
                ORDER BY target_minute DESC LIMIT ?
            ) ORDER BY target_minute""",(MAX_ROWS,)).fetchall()
        # At the cap the earliest represented date may be truncated.
        result=summarize(rows)
        if len(rows)==MAX_ROWS and result.get("days"):
            first_day=datetime.fromtimestamp(rows[0][0]*60,timezone.utc).date().isoformat()
            for day in result["days"]:
                if day["day_utc"]==first_day:
                    day["window_may_truncate_day"]=True
        return {**base,**result}
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,OverflowError):
        return {**base,"status":"DATA_REVIEW_REQUIRED","days":[]}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    print(json.dumps(run(p.parse_args().root),indent=2,allow_nan=False))
