"""Optional River prequential Futures replay with delayed labels and drift alarms.

No network, persistence, model promotion or order submission. Uses the same
validated local feature contract and five-minute target as LightGBM.
"""
import argparse,json,os
from collections import deque
from datetime import datetime,timezone
from . import futures_lightgbm as batch

VERSION="futures-river-1"
WARMUP=100

def factories():
    try:from river import compose,preprocessing,linear_model,optim,drift
    except ImportError:raise batch.ResearchError("İsteğe bağlı requirements-futures-ai.txt kurulmalı.") from None
    def model():
        return compose.Pipeline(preprocessing.StandardScaler(),
            linear_model.LinearRegression(optimizer=optim.SGD(.001),l2=.01))
    return model,lambda:drift.ADWIN(delta=.002)

def evaluate(raw,*,symbol,as_of,model_factory=None,detector_factory=None):
    rows=batch.validate(raw,symbol,as_of)
    if (model_factory is None)!=(detector_factory is None):
        raise batch.ResearchError("Model ve drift deneme adaptörleri birlikte gerekli.")
    injected=model_factory is not None
    if not injected:model_factory,detector_factory=factories()
    model=model_factory();detector=detector_factory()
    pending=deque();pred=[];actual=[];baseline=[];drifts=[]
    learned=0;last_learned=None;first_scored=None
    # Resolve labels only when their five-minute endpoint is observed.
    # Prediction at i follows learning through i, never i+1.
    for i,row in enumerate(rows):
        while pending and pending[0][0]+batch.HORIZON==i:
            j,x,guess,scored=pending.popleft()
            y=row["mid"]/rows[j]["mid"]-1
            if abs(y)>1:raise batch.ResearchError("Aşırı hedef fiyat değişimi.")
            if scored:
                pred.append(guess);actual.append(y);baseline.append(x["return_5m"])
                # Overlapping targets make this a diagnostic alarm, not a calibrated test.
                detector.update(min(1.0,abs(guess-y)))
                if detector.drift_detected:
                    drifts.append({"detected_at":row["at"].isoformat(),"prediction_at":rows[j]["at"].isoformat()})
            model.learn_one(x,y)
            learned+=1;last_learned=row["at"].isoformat()
        if i<20:continue
        x=dict(zip(batch.FEATURES,batch.features(rows,i)))
        guess=model.predict_one(x)
        guess=batch.numeric(0.0 if guess is None else guess,-1,1)
        scored=learned>=WARMUP
        if scored and first_scored is None:first_scored=row["at"].isoformat()
        pending.append((i,x,guess,scored))
    if len(actual)<50:raise batch.ResearchError("River ileri gözlem örneklemi eksik.")
    result=batch.metrics(pred,actual)
    zero=batch.metrics([0.0]*len(actual),actual)
    momentum=batch.metrics(baseline,actual)
    return {"version":VERSION,"status":"offline_prequential_research","symbol":symbol,
            "data_mode":"local_observations_unverified","observations":len(rows),
            "features":list(batch.FEATURES),"horizon_minutes":batch.HORIZON,
            "warmup_learned_labels":WARMUP,"learned_labels":learned,
            "scored_predictions":len(actual),"unresolved_predictions":len(pending),
            "first_scored_prediction_at":first_scored,"last_learned_target_at":last_learned,
            "metrics":{"river":result,"zero":zero,"trailing_momentum":momentum},
            "model_mae_below_both_baselines":result["mae_pct"]<min(zero["mae_pct"],momentum["mae_pct"]),
            "drift_detector":"ADWIN_absolute_error","drift_events":drifts,
            "drift_threshold_validated":False,"automatic_model_reset":False,
            "estimator_injected":injected,"runtime_verified":not injected,
            "feature_provenance_verified":False,"outcomes_overlap":True,
            "live_learning_enabled":False,"model_saved":False,"promotion_enabled":False,
            "profitability_verified":False,"actual_action":"HOLD","paper_orders":False,"real_orders":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True);p.add_argument("--symbol",choices=("BTCUSDT","ETHUSDT"),required=True)
    a=p.parse_args()
    try:
        if os.getenv("CYBERBOT_FUTURES_RIVER_ENABLED")!="1":raise batch.ResearchError("River araştırma izni kapalı.")
        print(json.dumps(evaluate(batch.read_local(a.input),symbol=a.symbol,as_of=datetime.now(timezone.utc)),
                         ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as exc:
        print(json.dumps({"status":"rejected","type":type(exc).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
