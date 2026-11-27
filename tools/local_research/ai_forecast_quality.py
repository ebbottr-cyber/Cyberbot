"""Heuristic forecast quality diagnostics, never a probability of success.

Only Chronos and the mean/AR1 references exist together prospectively in
this journal. Do not substitute retrospective River or LightGBM predictions.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

from .adaptive_review import finite, readonly, utc
from .journal_capacity import safe_stat

POLICY="forward-quality-1"
MIN_SCALE=1e-6


def assess(payload):
    base={"version":POLICY,"status":"INSUFFICIENT_METADATA","quality_score":None,
          "calibrated_probability":False,"three_ai_agreement_available":False,
          "automatic_action":False,"real_orders":False}
    if "quality_context" not in payload:
        return base
    try:
        if (payload["mode"]!="forward_shadow_research" or payload["context_bars"]!=21
                or payload["prediction_bars"]!=1 or payload["real_orders"] is not False
                or payload["automatic_promotion"] is not False):
            raise ValueError("unexpected evidence mode")
        ctx=payload["quality_context"]
        age,scale=ctx["last_observation_age_seconds"],ctx["mean_abs_context_return_pct"]
        last,lo,mid,hi=(payload[k] for k in ("last_price","p10","p50","p90"))
        pred=payload["predictions"]
        if set(pred)!={"naive","mean","ar1","chronos"} or pred["naive"]!=0:
            raise ValueError("unexpected predictions")
        if (not all(finite(v) for v in (age,scale,last,lo,mid,hi,*pred.values()))
                or not 0<lo<=mid<=hi or last<=0 or scale<0 or age<0
                or not math.isclose((mid/last-1)*100,pred["chronos"],rel_tol=1e-9,abs_tol=1e-9)):
            raise ValueError("invalid forecast context")
        if age>60:
            return {**base,"status":"STALE_CONTEXT"}
        if scale<MIN_SCALE:
            return {**base,"status":"INSUFFICIENT_VARIATION"}
        width=(hi-lo)/last*100
        vals=[pred[n] for n in ("mean","ar1","chronos")]
        spread=max(vals)-min(vals)
        wr,sr=width/scale,spread/scale
        if not all(math.isfinite(v) for v in (wr,sr)):
            raise ValueError("nonfinite normalized dispersion")
        # Explicit provisional thresholds: width / context movement, reference
        # disagreement / context movement, and age at forecast publication.
        parts={"interval_quality":40*max(0,1-wr/8),
               "reference_agreement":35*max(0,1-sr/3),
               "context_freshness":25*max(0,1-age/60)}
        score=round(sum(parts.values()))
        return {**base,"status":"DESCRIPTIVE_ONLY","quality_score":score,
                "components":{k:round(v,3) for k,v in parts.items()},
                "interval_width_pct":width,"reference_spread_pct":spread,
                "context_age_seconds":age,"width_to_context_scale":wr,
                "spread_to_context_scale":sr}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,ZeroDivisionError):
        return {**base,"status":"DATA_REVIEW_REQUIRED"}


def run(root, *, now=None):
    now=now or datetime.now(timezone.utc)
    path=Path(root)/"var/ai/forward-models-v2.sqlite3"
    base={"version":POLICY,"quality_score":None,"calibrated_probability":False,
          "automatic_action":False,"real_orders":False}
    try:
        for item in (path.parent.parent,path.parent,path):
            if safe_stat(item) is None:
                return {**base,"status":"NOT_AVAILABLE"}
        if not path.is_file() or path.stat().st_nlink!=1:
            raise ValueError("unsafe journal")
        with closing(readonly(path)) as db:
            row=db.execute("""SELECT target_minute,created_at,payload FROM forecasts
                WHERE market='FUTURES' AND symbol='BTCUSDT' AND source='binance-usdm-public'
                ORDER BY target_minute DESC LIMIT 1""").fetchone()
        if row is None:
            return {**base,"status":"NOT_AVAILABLE"}
        stamp=utc(row[1])
        if type(row[0]) is not int or row[0]!=int(stamp.timestamp()//60) or stamp.second>35 or stamp>now:
            raise ValueError("invalid forecast timing")
        result=assess(json.loads(row[2]))
        age=(now-stamp).total_seconds()
        # Historical quality is not a current signal. Suppress stale scores.
        if age>60:
            return {**base,"status":"STALE_FORECAST","last_forecast_utc":stamp.isoformat()}
        return {**result,"last_forecast_utc":stamp.isoformat()}
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return {**base,"status":"DATA_REVIEW_REQUIRED"}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    print(json.dumps(run(p.parse_args().root),indent=2,allow_nan=False))
