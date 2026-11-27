"""Local Futures live-data research orchestration, not autonomous trading.

Bounded collection session, followed by one offline evaluation. Optional
existing paper pilot observation and risk probe are separate explicit modes.
No scheduler installation, real orders, or automatic paper entry.
"""
import argparse,json,os,sqlite3
from datetime import timedelta
from . import futures_training as training,futures_lightgbm as batch
from . import futures_ai_consensus as ai,futures_ai_memory as memory
from . import futures_strategy_optimizer as optimizer,futures_dynamic_risk as risk
from . import futures_pilot as pilot,observed_pilot as stocks
from .providers import binance_observed as binance

VERSION="futures-live-research-1"
# Fixed-size windows advance by at least the previous test horizon; avoids
# repeatedly retraining on the same overlapping test interval.
WINDOW_ROWS=1200
FLAGS=("CYBERBOT_FUTURES_LIVE_RESEARCH_ENABLED","CYBERBOT_FUTURES_TRAINING_ENABLED",
       "CYBERBOT_FUTURES_AI_CONSENSUS_ENABLED","CYBERBOT_FUTURES_LIGHTGBM_ENABLED",
       "CYBERBOT_FUTURES_RIVER_ENABLED","CYBERBOT_FUTURES_AI_MEMORY_ENABLED",
       "CYBERBOT_FUTURES_STRATEGY_OPTIMIZER_ENABLED")
def base(symbol):
    training.symbol_check(symbol)
    return {"version":VERSION,"symbol":symbol,"status":"not_started",
            "actual_action":"HOLD","automatic_entry_enabled":False,
            "real_orders":False,"promotion_enabled":False,"profitability_verified":False,
            "live_forward_validation_verified":False,"model_weights_persisted":False}
def permitted():
    return training.enabled() and all(os.getenv(k)=="1" for k in FLAGS)

def evaluate_session(symbol,*,clock=stocks.utc,include_gemini=False):
    if not permitted():raise batch.ResearchError("Canlı araştırma izinleri kapalı.")
    if include_gemini and (os.getenv("CYBERBOT_FUTURES_GEMINI_ENABLED")!="1" or
                          os.getenv("CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED")!="1"):
        raise batch.ResearchError("Gemini paylaşım izinleri kapalı.")
    out=base(symbol);now=clock()
    rows=training.recent(symbol,clock=lambda:now)
    out["contiguous_rows"]=len(rows);out["required_rows"]=WINDOW_ROWS
    if len(rows)<WINDOW_ROWS:return {**out,"status":"waiting_for_contiguous_data"}
    rows=rows[-WINDOW_ROWS:]
    last=batch.timestamp(rows[-1]["at"])
    if not timedelta(0)<=now-last<=timedelta(minutes=2):
        return {**out,"status":"stale_training_data"}
    checked=batch.validate(rows,symbol,now)
    _,test,_=batch.split(batch.build(checked))
    first=checked[test[0][0]]["at"]
    previous=memory.snapshot(symbol)
    for state in previous["states"].values():
        end=state.get("last_end")
        if end and batch.timestamp(end)>first:
            return {**out,"status":"waiting_for_new_test_window",
                    "earliest_test_start_at":end,"current_test_start_at":first.isoformat()}
    # Do not claim independent evidence: both models and optimizer reuse this window.
    report=ai.run(rows,symbol=symbol,as_of=now)
    memory.compact(report,now)
    # Optimizer uses the prior memory; current window is not counted twice.
    strategy=optimizer.evaluate(rows,symbol=symbol,as_of=now,prior_memory=previous)
    saved=memory.record(report,clock=clock)
    if not saved["recorded"]:
        return {**out,"status":"concurrent_or_overlapping_evidence","memory":saved}
    current=memory.snapshot(symbol)
    excluded=optimizer.memory_exclusions(current,symbol,clock())
    # Newly quarantined models may veto a candidate, never promote one.
    candidate=strategy["next_research_candidate"]
    if candidate in excluded:candidate="cash"
    review={"status":"not_requested"}
    if include_gemini:review=ai.gemini_review(report)
    return {**out,"status":"research_completed","memory":saved,"ai":report,
            "strategy":strategy,"gemini":review,"next_research_candidate":candidate,
            "current_memory_exclusions":excluded,"shared_evaluation_data":True,
            "next_candidate_is_order":False}

def collect_session(symbol,cycles,*,clock=stocks.utc,include_gemini=False):
    if not permitted():raise batch.ResearchError("Canlı araştırma izinleri kapalı.")
    if include_gemini and (os.getenv("CYBERBOT_FUTURES_GEMINI_ENABLED")!="1" or
                          os.getenv("CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED")!="1"):
        raise batch.ResearchError("Gemini paylaşım izinleri kapalı.")
    result=training.run(symbol,cycles,clock=clock)
    if not any(r.get("status")=="recorded" for r in result["results"]):
        return {**base(symbol),"status":"no_new_observations","collection":result}
    return {**evaluate_session(symbol,clock=clock,include_gemini=include_gemini),"collection":result}

def paper_probe(symbol,*,clock=stocks.utc,include_risk=False):
    # One existing pilot observation; manual pending orders may be processed
    # and existing stops may close positions. Never invoke pilot.request.
    if os.getenv("CYBERBOT_FUTURES_LIVE_RESEARCH_ENABLED")!="1" or os.getenv("CYBERBOT_FUTURES_LIVE_PAPER_OBSERVE_ENABLED")!="1":
        raise batch.ResearchError("Sanal gözlem izni kapalı.")
    out=base(symbol)
    if pilot.symbol()!=symbol:raise batch.ResearchError("Sanal kasa sembolü uyuşmuyor.")
    if include_risk and os.getenv("CYBERBOT_FUTURES_DYNAMIC_RISK_ENABLED")!="1":
        raise batch.ResearchError("Dinamik risk izni kapalı.")
    d=binance.run(apply=True,clock=clock)
    if d.get("applied") is not True or d.get("real_orders") is not False:
        raise batch.ResearchError("Sanal gözlem sonucu geçersiz.")
    out.update(status="paper_observation_applied",paper_observation=d["ingress"],
               existing_manual_intents_may_be_processed=True,pilot=pilot.snapshot(clock=clock))
    if include_risk:
        try:out["risk"]=risk.run(clock=clock)
        except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as exc:
            out["risk"]={"status":"unavailable","error_type":type(exc).__name__,"actual_action":"HOLD"}
    return out

def status(symbol,*,clock=stocks.utc):
    return {**base(symbol),"status":"read_only","research_enabled":permitted(),
            "training":training.status(symbol,clock=clock),"memory":memory.snapshot(symbol),
            "paper_observe_enabled":os.getenv("CYBERBOT_FUTURES_LIVE_PAPER_OBSERVE_ENABLED")=="1"}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"))
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--collect-cycles",type=int);mode.add_argument("--evaluate",action="store_true")
    mode.add_argument("--paper-observe",action="store_true");mode.add_argument("--status",action="store_true")
    p.add_argument("--include-gemini",action="store_true");p.add_argument("--include-risk",action="store_true")
    a=p.parse_args()
    if a.include_risk and not a.paper_observe or a.include_gemini and not (a.evaluate or a.collect_cycles is not None):
        p.error("İsteğe bağlı araştırma modu uyuşmuyor.")
    try:
        if a.collect_cycles is not None:d=collect_session(a.symbol,a.collect_cycles,include_gemini=a.include_gemini)
        elif a.evaluate:d=evaluate_session(a.symbol,include_gemini=a.include_gemini)
        elif a.paper_observe:d=paper_probe(a.symbol,include_risk=a.include_risk)
        else:d=status(a.symbol)
        print(json.dumps(d,ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
