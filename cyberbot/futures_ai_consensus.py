"""Common-window Futures AI research, no ledger, promotion or order access."""
import argparse,json,os
from datetime import datetime,timezone
from statistics import mean
from . import futures_lightgbm as batch,futures_river as online,futures_gemini as gemini

VERSION="futures-ai-consensus-1"
MIN_NONOVERLAP=30

def summarize_pairs(a,b,y,baseline):
    metrics={"lightgbm":batch.metrics(a,y),"river":batch.metrics(b,y),
             "zero":batch.metrics([0.0]*len(y),y),"trailing_momentum":batch.metrics(baseline,y)}
    da=[batch.direction(v) for v in a];db=[batch.direction(v) for v in b]
    agree=[x==z for x,z in zip(da,db)]
    return {"examples":len(y),"metrics":metrics,
            "agreement_pct":mean(agree)*100,
            "both_hold":sum(x==z=="HOLD" for x,z in zip(da,db)),
            "both_directional":sum(x==z and x!="HOLD" for x,z in zip(da,db)),
            "disagreements":sum(not x for x in agree),
            "agreement_is_confidence_probability":False}

def evaluate(raw,*,symbol,as_of,batch_factory=None,online_factory=None,detector_factory=None):
    rows=batch.validate(raw,symbol,as_of)
    examples=batch.build(rows);train,test,purged=batch.split(examples)
    injected=any(f is not None for f in (batch_factory,online_factory,detector_factory))
    if injected and not all(f is not None for f in (batch_factory,online_factory,detector_factory)):
        raise batch.ResearchError("Üç deneme adaptörü birlikte gerekli.")
    if not injected:
        batch_factory=batch.estimator
        online_factory,detector_factory=online.factories()
    fixed=batch_factory();adaptive=online_factory();detector=detector_factory()
    fixed.fit([x for _,x,_ in train],[y for _,_,y in train])
    first=test[0][0]
    a=[batch.numeric(v,-1,1) for v in fixed.predict([x for _,x,_ in test])]
    if len(a)!=len(test):raise batch.ResearchError("LightGBM tahmin sayısı uyumsuz.")
    cursor=0;b=[];actual=[];baseline=[];alarms=[]
    last_learned=None
    for i,x,y in test:
        # Strictly before the prediction time; even a label ending at i is deferred.
        while cursor<len(examples) and examples[cursor][0]+batch.HORIZON<i:
            j,old_x,old_y=examples[cursor]
            adaptive.learn_one(dict(zip(batch.FEATURES,old_x)),old_y)
            last_learned=j+batch.HORIZON;cursor+=1
        guess=adaptive.predict_one(dict(zip(batch.FEATURES,x)))
        b.append(batch.numeric(0.0 if guess is None else guess,-1,1))
        actual.append(y);baseline.append(x[1])
    # Drift alarms are evaluated after outcomes resolve; diagnostic only.
    # Nonoverlapping five-minute target windows avoid reusing the same return intervals.
    selected=list(range(0,len(test),batch.HORIZON))
    for k in selected:
        detector.update(min(1.0,abs(b[k]-actual[k])))
        if detector.drift_detected:
            i=test[k][0]
            alarms.append({"prediction_at":rows[i]["at"].isoformat(),
                           "detected_at":rows[i+batch.HORIZON]["at"].isoformat()})
    all_metrics=summarize_pairs(a,b,actual,baseline)
    nonoverlap=summarize_pairs(*([seq[k] for k in selected] for seq in (a,b,actual,baseline)))
    n=nonoverlap["examples"];m=nonoverlap["metrics"]
    better={k:m[k]["mae_pct"]<min(m["zero"]["mae_pct"],m["trailing_momentum"]["mae_pct"])
            for k in ("lightgbm","river")}
    blockers=["unverified_feature_provenance","no_live_forward_validation","automatic_entry_disabled"]
    if n<MIN_NONOVERLAP:blockers.append("insufficient_nonoverlapping_examples")
    if not all(better.values()):blockers.append("baseline_not_beaten_by_both")
    if alarms:blockers.append("river_drift_alarm")
    return {"version":VERSION,"status":"offline_common_window_research","symbol":symbol,
            "data_mode":"local_observations_unverified","observations":len(rows),
            "horizon_minutes":batch.HORIZON,"features":list(batch.FEATURES),
            "training_examples":len(train),"purged_examples":purged,
            "training_last_target_at":rows[train[-1][0]+batch.HORIZON]["at"].isoformat(),
            "test_first_feature_at":rows[first]["at"].isoformat(),
            "test_last_target_at":rows[test[-1][0]+batch.HORIZON]["at"].isoformat(),
            "river_last_learned_target_at":rows[last_learned]["at"].isoformat() if last_learned is not None else None,
            "protocols":{"lightgbm":"fixed_purged_holdout","river":"causal_expanding_delayed_label"},
            "same_test_window":True,"all_test":all_metrics,"nonoverlapping_test":nonoverlap,
            "minimum_nonoverlapping_examples":MIN_NONOVERLAP,"both_baselines_beaten":better,
            "drift_events":alarms,"drift_threshold_validated":False,
            "estimator_injected":injected,"runtime_verified":not injected,
            "feature_provenance_verified":False,"independent_sources_verified":False,
            "blockers":blockers,"model_ranking":None,"gemini":{"status":"not_requested"},
            "profitability_verified":False,"promotion_enabled":False,"model_saved":False,
            "actual_action":"HOLD","paper_orders":False,"real_orders":False}

def gemini_review(report,*,transport=None):
    if os.getenv("CYBERBOT_FUTURES_GEMINI_ENABLED")!="1" or os.getenv("CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED")!="1":
        raise batch.ResearchError("Gemini araştırma ve dış veri paylaşım izinleri kapalı.")
    # Construct from our internally generated numeric report, never raw observations.
    common=report["nonoverlapping_test"]
    metrics={k:{field:batch.numeric(v[field],0,200 if field=="mae_pct" else 100)
                for field in ("mae_pct","direction_accuracy_pct")}
             for k,v in common["metrics"].items()}
    data={"symbol":report["symbol"],"horizon_minutes":5,"same_test_window":True,
          "nonoverlapping_examples":common["examples"],"metrics":metrics,
          "protocols":{"lightgbm":"fixed","river":"causal_online"},
          "drift_event_count":len(report["drift_events"]),"feature_provenance_verified":False,
          "profitability_verified":False}
    try:
        codes=gemini.request(os.getenv("CYBERBOT_GEMINI_MODEL",""),os.getenv("CYBERBOT_GEMINI_API_KEY",""),
                             gemini.payload(data),transport=transport)
    except batch.ResearchError:
        return {"status":"unavailable","requests_per_run_max":1,"automatic_retry":False,
                "provider_output_verified":False}
    selected=list(dict.fromkeys(["verify_data_provenance"]+codes))
    return {"status":"research_review_only","review_codes":selected,
            "review_tr":[gemini.TR[k] for k in selected],"requests_per_run_max":1,
            "automatic_retry":False,"provider_output_verified":False,"transport_mocked":transport is not None}

def run(raw,*,symbol,as_of,include_gemini=False,transport=None):
    flags=("CYBERBOT_FUTURES_AI_CONSENSUS_ENABLED","CYBERBOT_FUTURES_LIGHTGBM_ENABLED","CYBERBOT_FUTURES_RIVER_ENABLED")
    if any(os.getenv(f)!="1" for f in flags):raise batch.ResearchError("Ortak AI araştırma izinleri kapalı.")
    if include_gemini and (os.getenv("CYBERBOT_FUTURES_GEMINI_ENABLED")!="1" or
                           os.getenv("CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED")!="1"):
        raise batch.ResearchError("Gemini araştırma ve dış veri paylaşım izinleri kapalı.")
    d=evaluate(raw,symbol=symbol,as_of=as_of)
    if include_gemini:d["gemini"]=gemini_review(d,transport=transport)
    return d

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True);p.add_argument("--symbol",choices=("BTCUSDT","ETHUSDT"),required=True)
    p.add_argument("--include-gemini",action="store_true")
    a=p.parse_args()
    try:
        print(json.dumps(run(batch.read_local(a.input),symbol=a.symbol,as_of=datetime.now(timezone.utc),
                             include_gemini=a.include_gemini),ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
