"""Separate retrospective report histories and descriptive degradation flags.

The replay and rolling holdout reports can overlap; never treat successive
reports as independent observations or as proof of model drift.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from statistics import mean

from .adaptive_review import MODELS, readonly, utc
from .journal_capacity import safe_stat

LIMIT=60
SPECS={
    "river":("river-replay-journal.sqlite3","replay_reports","river-forward-replay-1",
             "retrospective_prequential","scored","river_version"),
    "lightgbm":("lightgbm-review-journal.sqlite3","training_reports","lightgbm-forward-review-1",
                "retrospective_holdout","test_samples","lightgbm_version"),
}


def history(root,name):
    filename,table,version,protocol,count_key,library_key=SPECS[name]
    base={"protocol":protocol,"reports_may_overlap":True,"independent_validation":False,
          "automatic_promotion":False,"real_orders":False}
    path=Path(root)/"var/ai"/filename
    reports=[]
    try:
        for part in (path.parent.parent,path.parent,path):
            if safe_stat(part) is None:
                return {**base,"status":"NOT_AVAILABLE","reports":[]}
        if not path.is_file() or path.stat().st_nlink!=1:
            raise ValueError("unsafe report journal")
        with closing(readonly(path)) as db:
            rows=db.execute("SELECT created_at,payload FROM "+table+
                            " ORDER BY created_at DESC,fingerprint DESC LIMIT ?",(LIMIT,)).fetchall()
        for stamp,raw in reversed(rows):
            p=json.loads(raw)
            date=utc(stamp)
            if (date>datetime.now(timezone.utc) or p["created_at"]!=stamp
                    or p["version"]!=version or p["market"]!="FUTURES" or p["symbol"]!="BTCUSDT"
                    or p["evidence_status"]!="EXPLORATORY_UNVERIFIED"
                    or any(p[k] is not False for k in ("live_prediction_verified","automatic_promotion",
                                                       "profitability_verified","real_orders"))):
                raise ValueError("invalid report")
            n=p[count_key]
            lib=p[library_key]
            if type(n) is not int or not 0<=n<=10000 or not isinstance(lib,str) or not 1<=len(lib)<=40 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-+" for c in lib):
                raise ValueError("invalid sample or version")
            metrics=p.get("paired_mae_pct",{})
            if metrics:
                if (set(metrics)!=set((*MODELS,name)) or not n
                        or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1e6 for v in metrics.values())):
                    raise ValueError("invalid metrics")
            elif n and (name=="river" or p.get("status")=="RESEARCH_MEASURED"):
                raise ValueError("missing measured metrics")
            reports.append({"created_at_utc":date.isoformat(),"samples":n,
                            "library_version":lib,"mae_pct":metrics,
                            "status":"RESEARCH_MEASURED" if metrics else "INSUFFICIENT_EVIDENCE"})
        return {**base,"status":"REPORTS_AVAILABLE" if reports else "NO_REPORT","reports":reports}
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return {**base,"status":"DATA_REVIEW_REQUIRED","reports":[]}


def degradation(forward):
    """Compare two disjoint groups of three eligible completed UTC dates.
    Descriptive flag only: samples and adjacent contexts remain correlated.
    Require recent dates and compare both absolute and baseline-relative MAE.
    """
    base={"automatic_action":False,"statistical_drift_verified":False,
          "min_days_per_window":3,"min_forecasts_per_day":20,
          "min_absolute_relative_increase_pct":25,
          "min_baseline_relative_ratio_increase_pct":20}
    if forward.get("status")!="RESEARCH_MEASURED":
        return {**base,"status":"INSUFFICIENT_EVIDENCE"}
    days=[d for d in forward["days"] if d["utc_day_ended"]
          and not d.get("window_may_truncate_day") and d["measured_forecasts"]>=20]
    if len(days)<6:
        return {**base,"status":"INSUFFICIENT_EVIDENCE"}
    days=days[-6:]
    dates=[datetime.fromisoformat(d["day_utc"]).date() for d in days]
    if (any((b-a).days!=1 for a,b in zip(dates,dates[1:]))
            or (datetime.now(timezone.utc).date()-dates[-1]).days>2):
        return {**base,"status":"INSUFFICIENT_RECENT_EVIDENCE"}
    old,new=days[:3],days[3:]
    def score(items):
        return mean(d["mae_pct"]["chronos"] for d in items),mean(d["mae_pct"]["naive"] for d in items)
    a,b=score(old)
    c,d=score(new)
    if min(a,b,d)<=0:
        return {**base,"status":"INSUFFICIENT_BASELINE"}
    absolute=(c/a-1)*100
    relative=((c/d)/(a/b)-1)*100
    if not all(math.isfinite(v) for v in (absolute,relative)):
        return {**base,"status":"INSUFFICIENT_BASELINE"}
    return {**base,"status":"REVIEW_DEGRADATION" if absolute>=25 and relative>=20 else "NO_THRESHOLD_BREACH",
            "prior_dates":[str(x) for x in dates[:3]],"recent_dates":[str(x) for x in dates[3:]],
            "prior_mae_pct":a,"recent_mae_pct":c,
            "absolute_mae_change_pct":absolute,"baseline_relative_ratio_change_pct":relative}


def snapshot(root,forward):
    return {"river_replay":history(root,"river"),"lightgbm_holdout":history(root,"lightgbm"),
            "chronos_degradation":degradation(forward),
            "cross_protocol_ranking":False,"real_orders":False}
