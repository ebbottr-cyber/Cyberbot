"""Explicit offline research-only logistic baseline; no saved model or production training."""
import argparse
import math
import json
import sqlite3
from tools.solana_learning_dataset import run as dataset,FEATURE_NAMES
from tools.solana_paper_replay import FALSE_FLAGS
from tools.solana_lightgbm_experiment import fit_lightgbm,OptionalModelUnavailable,PARAMS,ROUNDS

from tools.solana_river_experiment import fit_river
from tools.solana_model_consensus import analyze
from tools.solana_adaptive_weights import replay as adaptive_replay

MIN_EARLIER=100
MIN_LATER=50
MIN_CLASS=15
MIN_MINTS=5

def sigmoid(x):
    return 1/(1+math.exp(-max(-35,min(35,x))))

def prepare(rows):
    return [([float(r["features"][k]) for k in FEATURE_NAMES],int(r["label"]["positive_quote_net"])) for r in rows]

def fit(train):
    n=len(train);d=len(FEATURE_NAMES)
    means=[sum(x[j] for x,y in train)/n for j in range(d)]
    scales=[math.sqrt(sum((x[j]-means[j])**2 for x,y in train)/n) or 1 for j in range(d)]
    def transform(x):
        return [1.0]+[max(-10,min(10,(v-m)/s)) for v,m,s in zip(x,means,scales)]
    prepared=[(transform(x),y) for x,y in train]
    w=[0.0]*(d+1)
    for _ in range(200):
        gradient=[0.0]*(d+1)
        for x,y in prepared:
            error=sigmoid(sum(a*b for a,b in zip(w,x)))-y
            for j,v in enumerate(x):gradient[j]+=error*v
        for j in range(d+1):
            w[j]-=0.05*(gradient[j]/n+(0.01*w[j] if j else 0))
    def predict(x):return sigmoid(sum(a*b for a,b in zip(w,transform(x))))
    return predict

def metrics(data,predict):
    tp=tn=fp=fn=0;brier=0.0;loss=0.0
    for x,y in data:
        p=predict(x)
        if not math.isfinite(p) or not 0<=p<=1:raise ValueError("Invalid prediction")
        positive=p>=0.5
        tp+=positive and y==1;tn+=not positive and y==0
        fp+=positive and y==0;fn+=not positive and y==1
        brier+=(p-y)**2
        q=max(1e-12,min(1-1e-12,p))
        loss-=y*math.log(q)+(1-y)*math.log(1-q)
    n=len(data)
    return {"samples":n,"true_positive":tp,"true_negative":tn,"false_positive":fp,"false_negative":fn,
            "accuracy":(tp+tn)/n,"balanced_accuracy":((tp/(tp+fn))+(tn/(tn+fp)))/2,
            "brier_score":brier/n,"log_loss":loss/n}

def evaluate(report,*,allow_experiment=False,include_lightgbm=False,include_river=False,include_adaptive=False):
    if type(allow_experiment) is not bool or type(include_lightgbm) is not bool or type(include_river) is not bool or type(include_adaptive) is not bool:raise ValueError("Explicit experiment flag required")
    if report.get("source_scope")!="dexterm_bridge_only" or report.get("research_only") is not True:
        raise ValueError("Unexpected dataset scope")
    if any(report.get(k) is not False for k in ("training_allowed","training_performed","model_promoted","real_orders","labels_are_real_fills")):
        raise ValueError("Unexpected dataset flags")
    if report.get("feature_names")!=list(FEATURE_NAMES):raise ValueError("Unexpected feature schema")
    rows=report["examples"]
    if not isinstance(rows,list) or len(rows)>1500 or len(rows)!=report["example_count"]:raise ValueError("Invalid example count")
    groups={k:[] for k in ("earlier","later")}
    for r in rows:
        if set(r["features"])!=set(FEATURE_NAMES) or any(type(v) is not int or abs(v)>10**24 for v in r["features"].values()):
            raise ValueError("Invalid features")
        if type(r["label"]["positive_quote_net"]) is not bool:raise ValueError("Invalid label")
        groups[r["partition"]].append(r)
    blockers=[]
    for name,minimum in (("earlier",MIN_EARLIER),("later",MIN_LATER)):
        group=groups[name];pos=sum(r["label"]["positive_quote_net"] for r in group)
        if len(group)<minimum:blockers.append(name+"_sample_count")
        if min(pos,len(group)-pos)<MIN_CLASS:blockers.append(name+"_class_support")
        if len({r["mint"] for r in group})<MIN_MINTS:blockers.append(name+"_mint_diversity")
    if report.get("bridge_history_truncated"):blockers.append("archive_window_truncated")
    if not allow_experiment:blockers.append("explicit_experiment_opt_in_required")
    out={"status":"experiment_blocked","research_only":True,"network_requests":False,
         "dataset_sha256":report["dataset_sha256"],"blockers":blockers,
         "experimental_fit_performed":False,"training_allowed":False,"production_training_performed":False,
         "weights_updated":False,"model_saved":False,"model_promoted":False,
         "independent_holdout_verified":False,"winner":None,"results":[],
         "consensus":{"status":"blocked_by_experiment_gate","trade_eligible":False},
         "adaptive_weights":{"status":"blocked_by_experiment_gate" if include_adaptive else "not_requested","trade_eligible":False},
         "lightgbm_status":"blocked_by_experiment_gate" if include_lightgbm else "not_requested",
         "river_status":"blocked_by_experiment_gate" if include_river else "not_requested",**FALSE_FLAGS}
    if blockers:return out
    train=prepare(groups["earlier"]);test=prepare(groups["later"])
    prior=sum(y for x,y in train)/len(train)
    predictor=fit(train)
    static_predictions={"logistic_baseline":[predictor(x) for x,y in test]}
    out.update(status="experiment_complete",experimental_fit_performed=True,
               results=[{"model":name,"later_window":metrics(test,p)}
                        for name,p in (("constant_training_prior",lambda x:prior),
                                       ("logistic_baseline",predictor))])
    if include_lightgbm:
        try:
            predictions,version=fit_lightgbm(train,test)
            if len(predictions)!=len(test):raise ValueError("Prediction length mismatch")
            values=iter(predictions)
            score=metrics(test,lambda x:next(values))
            out["results"].append({"model":"lightgbm","version":version,"parameters":dict(PARAMS),
                                   "boost_rounds":ROUNDS,"later_window":score})
            static_predictions["lightgbm"]=list(predictions)
            out["lightgbm_status"]="experiment_complete"
        except (OptionalModelUnavailable,ValueError) as e:
            out["lightgbm_status"]="unavailable_or_failed"
            out["lightgbm_reason"]=str(e) if isinstance(e,OptionalModelUnavailable) else "invalid_predictions"
            out["status"]="experiment_partial"
    out["consensus"]=analyze([y for x,y in test],static_predictions)
    if include_adaptive:
        try:
            out["adaptive_weights"]=adaptive_replay(groups["later"],static_predictions,split_timestamp=report.get("split_timestamp"))
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError):
            out["adaptive_weights"]={"status":"invalid_replay_inputs","trade_eligible":False}
            out["status"]="experiment_partial"
    if include_river:
        try:
            predictions,version,details=fit_river(groups["earlier"],groups["later"],split_timestamp=report["split_timestamp"])
            if len(predictions)!=len(test):raise ValueError("Prediction length mismatch")
            values=iter(predictions)
            score=metrics(test,lambda x:next(values))
            out["results"].append({"model":"river_logistic","version":version,"later_window":score,
                                   "evaluation_details":details,"direct_static_comparison":False})
            out["river_status"]="experiment_complete"
        except (OptionalModelUnavailable,ValueError,KeyError,TypeError) as e:
            out["river_status"]="unavailable_or_failed"
            out["river_reason"]=str(e) if isinstance(e,OptionalModelUnavailable) else "invalid_replay_inputs_or_predictions"
            out["status"]="experiment_partial"
    return out

def run(database,*,limit=500,allow_experiment=False,include_lightgbm=False,include_river=False,include_adaptive=False):
    return evaluate(dataset(database,limit=limit),allow_experiment=allow_experiment,include_lightgbm=include_lightgbm,include_river=include_river,include_adaptive=include_adaptive)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--limit",type=int,default=500)
    p.add_argument("--allow-experiment",action="store_true")
    p.add_argument("--include-lightgbm",action="store_true")
    p.add_argument("--include-river",action="store_true")
    p.add_argument("--include-adaptive",action="store_true")
    a=p.parse_args()
    try:
        print(json.dumps(run(a.database,limit=a.limit,allow_experiment=a.allow_experiment,include_lightgbm=a.include_lightgbm,include_river=a.include_river,include_adaptive=a.include_adaptive),indent=2,allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,"training_allowed":False,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
