"""Optional River delayed-label research replay. No persisted weights or live updates."""
import heapq
import math
from itertools import groupby
from tools.dexterm_learning_dataset import FEATURE_NAMES
from tools.dexterm_paper_replay import instant
from tools.dexterm_lightgbm_experiment import OptionalModelUnavailable

SCALES=(100_000_000,1000,1000,3600)

def features(row):
    return {k:max(-10.0,min(10.0,float(row["features"][k])/scale))
            for k,scale in zip(FEATURE_NAMES,SCALES)}

def replay(earlier,later,model,*,split_timestamp):
    cut=instant(split_timestamp)
    events=[]
    seen=set()
    for part,rows in (("earlier",earlier),("later",later)):
        for i,r in enumerate(rows):
            start=instant(r["feature_at"]);end=instant(r["label_at"])
            if not 180<=(end-start).total_seconds()<=3600:
                raise ValueError("Invalid label horizon")
            if (part=="earlier" and end>=cut) or (part=="later" and start<cut):
                raise ValueError("Partition chronology mismatch")
            key=(r["mint"],start)
            if key in seen:raise ValueError("Duplicate feature event")
            seen.add(key)
            events.append((start,r["mint"],part,i,end,features(r),r["label"]["positive_quote_net"]))
    events.sort(key=lambda e:(e[0],e[1]))
    pending=[];seq=0;updates=0;predictions=[None]*len(later)
    for stamp,batch in groupby(events,key=lambda e:e[0]):
        # Labels at exactly the prediction timestamp are withheld until the
        # next batch, avoiding within-timestamp ordering assumptions.
        while pending and pending[0][0]<stamp:
            _,_,x,y=heapq.heappop(pending)
            model.learn_one(x,y)
            updates+=1
        for _,mint,part,i,end,x,y in batch:
            if part=="later":
                probs=model.predict_proba_one(x)
                value=float(probs.get(True,0.5))
                if not math.isfinite(value) or not 0<=value<=1:
                    raise ValueError("Invalid River prediction")
                predictions[i]=value
            heapq.heappush(pending,(end,seq,x,y))
            seq+=1
    if any(p is None for p in predictions):raise ValueError("Missing prediction")
    return predictions,{"updates_before_last_prediction_batch":updates,"pending_labels_at_end":len(pending),
                        "label_availability":"strictly_before_prediction_timestamp",
                        "evaluation_mode":"delayed_prequential","fixed_test_weights":False}

def fit_river(earlier,later,*,split_timestamp):
    try:
        import river
        from river import linear_model,optim
    except (ImportError,OSError) as e:
        raise OptionalModelUnavailable("river_dependency_unavailable") from e
    try:
        model=linear_model.LogisticRegression(optimizer=optim.SGD(0.01),l2=0.01)
        values,details=replay(earlier,later,model,split_timestamp=split_timestamp)
    except (ValueError,TypeError,AttributeError,ArithmeticError,RuntimeError) as e:
        raise OptionalModelUnavailable("river_replay_failed") from e
    return values,str(getattr(river,"__version__","unknown")),details
