"""Offline agreement diagnostics on aligned static model predictions, never order signals."""
import math
from tools.dexterm_paper_replay import FALSE_FLAGS

LOW=0.30
HIGH=0.70
MAX_SPREAD=0.20
REQUIRED=("logistic_baseline","lightgbm")

def analyze(labels,predictions):
    if not isinstance(labels,list) or not 1<=len(labels)<=1500 or any(type(y) is not int or y not in (0,1) for y in labels):
        raise ValueError("Invalid evaluation labels")
    if not isinstance(predictions,dict) or set(predictions)-set(REQUIRED):
        raise ValueError("Only aligned static predictions supported")
    for values in predictions.values():
        if not isinstance(values,list) or len(values)!=len(labels) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in values):
            raise ValueError("Invalid aligned probabilities")
    n=len(labels)
    out={"status":"consensus_blocked","missing_models":[m for m in REQUIRED if m not in predictions],
         "evaluation_mode":"fixed_earlier_window_fit","sample_count":n,
         "thresholds":{"low":LOW,"high":HIGH,"maximum_spread":MAX_SPREAD},
         "required_models":list(REQUIRED),"river_in_static_consensus":False,
         "gemini_in_numeric_consensus":False,"research_only":True,
         "network_requests":False,"trade_eligible":False,"model_promoted":False,
         "independent_holdout_verified":False,"weights_updated":False,**FALSE_FLAGS}
    if out["missing_models"]:return out
    counts={"joint_positive":0,"joint_nonpositive":0,"disagreement":0,"uncertain":0}
    correct=0;covered=0;squared=0.0
    for y,a,b in zip(labels,predictions[REQUIRED[0]],predictions[REQUIRED[1]]):
        squared+=((a+b)/2-y)**2
        # The thresholds are fixed research hypotheses. Abstention is retained
        # as a separate outcome, not counted as a correct negative.
        if (a>=0.5)!=(b>=0.5) or abs(a-b)>MAX_SPREAD+1e-12:
            category="disagreement"
        elif min(a,b)>=HIGH:
            category="joint_positive"
        elif max(a,b)<=LOW:
            category="joint_nonpositive"
        else:
            category="uncertain"
        counts[category]+=1
        if category in ("joint_positive","joint_nonpositive"):
            covered+=1
            correct+=(category=="joint_positive")==bool(y)
    out.update(status="consensus_diagnostic_complete",counts=counts,
               covered_samples=covered,abstained_samples=n-covered,
               coverage_pct=100*covered/n,
               covered_accuracy=correct/covered if covered else None,
               mean_probability_brier=squared/n,
               thresholds_calibrated=False,probabilities_calibrated=False)
    return out
