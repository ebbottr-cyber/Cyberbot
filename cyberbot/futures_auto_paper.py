"""Opt-in one-cycle automated PAPER entry. No authenticated exchange endpoints."""
import argparse,json,os,sqlite3
from contextlib import closing
from datetime import timedelta
from decimal import Decimal as D
from . import futures_pilot as fut,futures_forward_memory as forward
from . import futures_ai_bridge as bridge,futures_lightgbm as batch
from . import futures_ai_memory as memory,futures_dynamic_risk as risk
from . import observed_pilot as stocks,futures_strategy_gate as strategy_gate
from .providers import binance_observed as binance

VERSION="futures-auto-paper-1"
MIN_SCORED=100
MIN_DIRECTIONAL=10
LOOKBACK=timedelta(days=2)

def result(symbol,status,**kw):
    return {"version":VERSION,"symbol":symbol,"status":status,"real_orders":False,
            "exchange_execution_verified":False,"profitability_verified":False,**kw}

def evidence(symbol,now):
    p=forward.path()
    if not p.is_file():return None,None
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
        if not forward.schema(db):return None,None
        rows=db.execute("SELECT feature_at,target_at,issued_at,status,payload FROM "+forward.TABLE+
                        " WHERE symbol=? AND feature_at>=? ORDER BY feature_at DESC LIMIT ?",
                        (symbol,(now-LOOKBACK).isoformat(),forward.KEEP)).fetchall()
    scored=[];missing=0;candidate=None;later=None
    versions={"lightgbm":batch.VERSION,"river":bridge.online.VERSION,"forecast":bridge.VERSION}
    for feature,target,issued,status,payload in rows:
        a=batch.timestamp(feature);z=batch.timestamp(target);t=stocks.ts(issued);d=json.loads(payload)
        if z-a!=batch.HORIZON*batch.STEP or not a<=t<=a+timedelta(seconds=forward.MAX_ISSUE_AGE) or t>now or (later and z>later) or d.get("model_versions")!=versions:
            return None,None
        later=a
        if status=="pending":
            if z<=now:
                if now>=z+timedelta(seconds=forward.GRACE):return None,None
                continue
            if candidate is None and 0<=(now-a).total_seconds()<=bridge.MAX_FEATURE_AGE:
                candidate={"feature_at":feature,"target_at":target,"issued_at":issued,
                           "feature_mid":batch.numeric(d["feature_mid"],1e-8,1e9),
                           "lightgbm_return":batch.numeric(d["predictions"]["lightgbm"],-1,1),
                           "river_return":batch.numeric(d["predictions"]["river"],-1,1),"estimator_injected":False}
        elif status=="missing":
            if z>now:return None,None
            missing+=1
        elif status=="scored":
            if z>now or not t<stocks.ts(d["target_received_at"])<z or not z<=stocks.ts(d["resolved_at"])<=now:return None,None
            scored.append(d)
        else:return None,None
    n=len(scored)
    if n<MIN_SCORED or n/(n+missing)<.95:return None,candidate
    actual=[batch.numeric(d["actual_return"],-1,1) for d in scored]
    baseline=min(batch.metrics([batch.numeric(d["predictions"][k],-1,1) for d in scored],actual)["mae_pct"] for k in ("zero","trailing_momentum"))
    for k in ("lightgbm","river"):
        predictions=[batch.numeric(d["predictions"][k],-1,1) for d in scored]
        if batch.metrics(predictions,actual)["mae_pct"]>=baseline:return None,candidate
        directional=[(batch.direction(x),batch.direction(y)) for x,y in zip(predictions,actual) if batch.direction(x)!="HOLD"]
        if len(directional)<MIN_DIRECTIONAL or sum(a==b for a,b in directional)/len(directional)<.5:return None,candidate
    return {"scored":n,"missing":missing,"coverage_pct":100*n/(n+missing)},candidate

def run(symbol,*,clock=stocks.utc):
    if not fut.auto_enabled() or not forward.permitted() or any(os.getenv(k)!="1" for k in bridge.FLAGS):
        raise batch.ResearchError("Otomatik sanal giriş izinleri kapalı.")
    if fut.symbol()!=symbol:raise batch.ResearchError("Sembol uyuşmuyor.")
    # Observe existing exits first. One public quote cycle, no automatic retries.
    obs=binance.run(apply=True,clock=clock,auto_paper=True)
    s=fut.snapshot(clock=clock)
    if s["position"] or s["pending"]:return result(symbol,"position_or_pending",observation=obs["ingress"])
    now=clock();proof,pred=evidence(symbol,now)
    if not proof or not pred:return result(symbol,"waiting_for_forward_evidence",observation=obs["ingress"])
    if not strategy_gate.allowed(symbol,clock=clock):return result(symbol,"strategy_gate_veto")
    at=batch.timestamp(pred["feature_at"])
    if not bridge.memory_ready(memory.snapshot(symbol),symbol,at):return result(symbol,"memory_veto")
    if batch.direction(pred["lightgbm_return"])!=batch.direction(pred["river_return"]) or batch.direction(pred["lightgbm_return"])=="HOLD":
        return result(symbol,"ai_disagreement_or_hold")
    report=risk.run(clock=clock)
    # Recheck evidence after research work, then repeat inside serialized ledger transaction.
    def gate(now):
        new,p=evidence(symbol,now)
        return bool(new and p==pred and bridge.memory_ready(memory.snapshot(symbol),symbol,at) and strategy_gate.allowed(symbol,clock=lambda:now))
    candidate=bridge.combine(symbol,pred,report,clock(),entry_halted=False)
    if candidate["status"]!="shadow_candidate":return result(symbol,"risk_veto",blockers=candidate["blockers"])
    queued=fut.queue_auto(candidate,gate=gate,clock=clock)
    return result(symbol,"paper_intent_queued",intent=queued,evidence=proof,
                  fill_requires_next_observation=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"));a=p.parse_args()
    try:print(json.dumps(run(a.symbol),ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
