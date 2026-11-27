"""Futures AI shadow signal bridge. No request, ledger write, or model promotion."""
import argparse,json,os,sqlite3
from datetime import timedelta
from . import futures_lightgbm as batch,futures_river as online
from . import futures_ai_memory as memory,futures_training as training
from . import futures_dynamic_risk as risk,futures_pilot as pilot
from . import observed_pilot as stocks
from .pilot_control import snapshot as control_snapshot

VERSION="futures-ai-bridge-1"
WINDOW=1200
MAX_FEATURE_AGE=90
MIN_MEMORY_RUNS=2
FLAGS=("CYBERBOT_FUTURES_AI_BRIDGE_ENABLED","CYBERBOT_FUTURES_LIGHTGBM_ENABLED",
       "CYBERBOT_FUTURES_RIVER_ENABLED","CYBERBOT_FUTURES_AI_MEMORY_ENABLED",
       "CYBERBOT_FUTURES_DYNAMIC_RISK_ENABLED")
def base(symbol):
    return {"version":VERSION,"symbol":symbol,"status":"HOLD","blockers":[],
            "research_candidate":None,"actual_action":"HOLD","paper_orders":False,
            "real_orders":False,"automatic_entry_enabled":False,"promotion_enabled":False,
            "live_forward_validation_verified":False,"profitability_verified":False}
def blocked(out,reason):
    out["blockers"].append(reason);return out

def memory_ready(snap,symbol,feature_at):
    if (snap.get("version")!=memory.VERSION or snap.get("symbol")!=symbol
        or snap.get("data_mode")!="local_observations_unverified"):return False
    recent=snap.get("recent",[])
    if len(recent)<MIN_MEMORY_RUNS:return False
    evidence=recent[:MIN_MEMORY_RUNS]
    later=None
    for e in evidence:
        start=batch.timestamp(e["start"]);end=batch.timestamp(e["end"])
        if e.get("symbol")!=symbol or not start<end<feature_at or feature_at-end>timedelta(days=2) or (later is not None and end>later):
            return False
        later=start
        if type(e["examples"]) is not int or e["examples"]<30 or e["drift_count"]!=0:return False
        m=e["metrics"]
        for k in memory.MODELS:
            if batch.numeric(m[k]["mae_pct"],0,200)>=min(batch.numeric(m[j]["mae_pct"],0,200) for j in ("zero","trailing_momentum")):return False
    for k in memory.MODELS:
        s=snap["states"][k]
        if s.get("status")!="observing" or s.get("runs",0)<MIN_MEMORY_RUNS or s.get("weak_streak")!=0 or s.get("last_end")!=evidence[0]["end"]:return False
    return True

def forecast(rows,*,batch_factory=None,online_factory=None):
    if (batch_factory is None)!=(online_factory is None):raise batch.ResearchError("İki deneme modeli gerekli.")
    injected=batch_factory is not None
    if not injected:batch_factory=batch.estimator;online_factory,_=online.factories()
    examples=batch.build(rows);train,_,_=batch.split(examples)
    i=len(rows)-1
    x=batch.features(rows,i)
    fixed=batch_factory();adaptive=online_factory()
    fixed.fit([a for _,a,_ in train],[y for _,_,y in train])
    for j,a,y in examples:
        if j+batch.HORIZON<i:adaptive.learn_one(dict(zip(batch.FEATURES,a)),y)
    values=list(fixed.predict([x]))
    if len(values)!=1:raise batch.ResearchError("Tahmin sayısı geçersiz.")
    r=adaptive.predict_one(dict(zip(batch.FEATURES,x)))
    a=batch.numeric(values[0],-1,1);b=batch.numeric(0 if r is None else r,-1,1)
    return {"lightgbm_return":a,"river_return":b,"lightgbm_direction":batch.direction(a),
            "river_direction":batch.direction(b),"feature_at":rows[i]["at"].isoformat(),
            "feature_mid":rows[i]["mid"],"estimator_injected":injected}

def combine(symbol,pred,report,now,*,entry_halted):
    out=base(symbol);out["forecast"]=pred
    at=batch.timestamp(pred["feature_at"])
    if not 0<=(now-at).total_seconds()<=MAX_FEATURE_AGE:return blocked(out,"stale_ai_features")
    if entry_halted is not False:return blocked(out,"kill_switch")
    a=batch.direction(batch.numeric(pred["lightgbm_return"],-1,1))
    b=batch.direction(batch.numeric(pred["river_return"],-1,1))
    if pred.get("estimator_injected") is not False:return blocked(out,"injected_estimator")
    if a!=b or a=="HOLD":return blocked(out,"ai_disagreement_or_hold")
    if (report.get("version")!=risk.VERSION or report.get("symbol")!=symbol
        or report.get("status")!="research_proposal" or report.get("blockers")!=[]
        or report.get("actual_action")!="HOLD" or any(report.get(k) is not False for k in ("real_orders","paper_orders","pilot_applied"))):
        return blocked(out,"risk_not_confirmed")
    if not 0<=(now-stocks.ts(report["evaluated_at"])).total_seconds()<=30:return blocked(out,"stale_risk_report")
    q=report.get("quote_reference",{})
    if q.get("source")!="binance-usdm-public":return blocked(out,"risk_quote_source_mismatch")
    qt=stocks.ts(q["source_at"])
    if not 0<=(now-qt).total_seconds()<=30 or abs((qt-at).total_seconds())>MAX_FEATURE_AGE:
        return blocked(out,"risk_quote_time_mismatch")
    mid=batch.numeric(q["mid"],1e-8,1e9)
    if abs(mid/batch.numeric(pred["feature_mid"],1e-8,1e9)-1)>.002:
        return blocked(out,"risk_quote_price_mismatch")
    p=report["proposal"];side="LONG" if a=="UP" else "SHORT"
    if p.get("side")!=side:return blocked(out,"technical_direction_disagreement")
    # Return the dynamic risk proposal as research metadata, not a manual intent.
    out.update(status="shadow_candidate",research_candidate=side,risk_proposal=p,
               risk_quote_reference=q,valid_until=(min(at+timedelta(seconds=MAX_FEATURE_AGE),
               qt+timedelta(seconds=30),stocks.ts(report["evaluated_at"])+timedelta(seconds=30))).isoformat())
    return out

def run(symbol,*,clock=stocks.utc):
    training.symbol_check(symbol)
    if any(os.getenv(f)!="1" for f in FLAGS) or not training.enabled() or not pilot.enabled():
        raise batch.ResearchError("AI köprü izinleri kapalı.")
    if pilot.symbol()!=symbol:raise batch.ResearchError("Sanal kasa sembolü uyuşmuyor.")
    now=clock();out=base(symbol)
    raw=training.recent(symbol,clock=lambda:now)
    if len(raw)<WINDOW:return blocked(out,"insufficient_contiguous_data")
    rows=batch.validate(raw[-WINDOW:],symbol,now);at=rows[-1]["at"]
    if not 0<=(now-at).total_seconds()<=MAX_FEATURE_AGE:return blocked(out,"stale_ai_features")
    if control_snapshot()["halted"]:return blocked(out,"kill_switch")
    snap=memory.snapshot(symbol)
    if not memory_ready(snap,symbol,at):return blocked(out,"insufficient_or_quarantined_memory")
    pred=forecast(rows)
    if not 0<=(clock()-at).total_seconds()<=MAX_FEATURE_AGE:return blocked(out,"stale_ai_features")
    if pred["lightgbm_direction"]!=pred["river_direction"] or pred["lightgbm_direction"]=="HOLD":
        return blocked(out,"ai_disagreement_or_hold")
    report=risk.run(clock=clock)
    # Re-read local vetoes after network/CPU work. Not an atomic execution authorization.
    if not memory_ready(memory.snapshot(symbol),symbol,at):return blocked(out,"memory_changed")
    return combine(symbol,pred,report,clock(),entry_halted=control_snapshot()["halted"])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"))
    a=p.parse_args()
    try:
        print(json.dumps(run(a.symbol),ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as exc:
        print(json.dumps({"status":"rejected","type":type(exc).__name__,"actual_action":"HOLD","real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
