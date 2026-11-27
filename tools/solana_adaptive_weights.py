"""Delayed-label adaptive mixture diagnostics. Weights are transient and never deployed."""
import heapq
import math
from itertools import groupby
from tools.solana_paper_replay import instant,FALSE_FLAGS
from tools.solana_model_consensus import REQUIRED

MIN_MATURE=20
MIN_WEIGHT=0.25
MAX_WEIGHT=0.75
PRIOR_COUNT=20

def replay(rows,predictions,*,split_timestamp):
    if not isinstance(rows,list) or not 1<=len(rows)<=1500:raise ValueError("Invalid evaluation rows")
    if not isinstance(predictions,dict) or set(predictions)-set(REQUIRED):raise ValueError("Unexpected model")
    for values in predictions.values():
        if not isinstance(values,list) or len(values)!=len(rows) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in values):
            raise ValueError("Invalid aligned probabilities")
    out={"status":"adaptive_weights_blocked","missing_models":[m for m in REQUIRED if m not in predictions],
         "research_only":True,"network_requests":False,"trade_eligible":False,
         "model_promoted":False,"weights_updated":False,"production_weights_changed":False,
         "independent_holdout_verified":False,"evaluation_mode":"delayed_prequential_mixture",
         "direct_static_comparison":False,"minimum_mature_labels":MIN_MATURE,
         "weight_bounds":[MIN_WEIGHT,MAX_WEIGHT],**FALSE_FLAGS}
    if out["missing_models"]:return out
    cut=instant(split_timestamp)
    events=[];seen=set()
    for i,r in enumerate(rows):
        start=instant(r["feature_at"]);end=instant(r["label_at"]);y=r["label"]["positive_quote_net"]
        key=(r["mint"],start)
        if r["partition"]!="later" or start<cut or not 180<=(end-start).total_seconds()<=3600 or type(y) is not bool or key in seen:
            raise ValueError("Invalid evaluation chronology")
        seen.add(key)
        events.append((start,r["mint"],i,end,int(y)))
    events.sort(key=lambda e:(e[0],e[1]))
    pending=[];loss_a=loss_b=0.0;mature=0
    weighted_error=equal_error=0.0;trace=[];adapted_samples=0
    a,b=(predictions[m] for m in REQUIRED)
    for stamp,batch in groupby(events,key=lambda e:e[0]):
        # Equal-time labels are withheld until a strictly later prediction.
        while pending and pending[0][0]<stamp:
            _,_,ea,eb=heapq.heappop(pending)
            loss_a+=ea;loss_b+=eb;mature+=1
        w=0.5
        if mature>=MIN_MATURE:
            # Shrink empirical Brier errors toward a neutral 0.25 prior.
            sa=(loss_a+PRIOR_COUNT*0.25)/(mature+PRIOR_COUNT)
            sb=(loss_b+PRIOR_COUNT*0.25)/(mature+PRIOR_COUNT)
            w=max(MIN_WEIGHT,min(MAX_WEIGHT,sb/(sa+sb)))
        for _,mint,i,end,y in batch:
            pred=w*a[i]+(1-w)*b[i]
            equal=(a[i]+b[i])/2
            weighted_error+=(pred-y)**2;equal_error+=(equal-y)**2
            adapted_samples+=mature>=MIN_MATURE
            trace.append({"index":i,"feature_at":stamp.isoformat(),"mature_labels":mature,
                          "logistic_weight":w,"lightgbm_weight":1-w,"research_probability":pred})
            heapq.heappush(pending,(end,i,(a[i]-y)**2,(b[i]-y)**2))
    n=len(rows)
    out.update(status="adaptive_weights_diagnostic_complete",sample_count=n,
               adaptive_samples=adapted_samples,pending_labels_at_end=len(pending),
               mature_labels_before_last_batch=mature,adaptive_brier=weighted_error/n,
               equal_weight_brier=equal_error/n,weight_trace=trace,
               experimental_adaptation_observed=adapted_samples>0,
               weight_policy_calibrated=False,performance_improvement_verified=False)
    return out
