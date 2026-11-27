"""Manual Gemini-compatible research review exchange; no API, secrets or trading authority."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from tools.dexterm_research_archive import MAX_BYTES
from tools.dexterm_paper_replay import FALSE_FLAGS

MODELS=("constant_training_prior","logistic_baseline","lightgbm","river_logistic")
BLOCKERS={"earlier_sample_count","later_sample_count","earlier_class_support","later_class_support",
          "earlier_mint_diversity","later_mint_diversity","archive_window_truncated",
          "explicit_experiment_opt_in_required"}
FINDINGS={"insufficient_samples","class_imbalance","limited_mint_diversity",
          "missing_model_results","baseline_comparison_needed","calibration_review_needed",
          "delayed_online_not_static_comparable","quote_labels_not_fills",
          "independent_holdout_required","additional_cost_testing_required"}
CHECKS={"collect_more_observations","review_label_coverage","review_class_balance",
        "review_calibration","compare_static_baselines","separate_online_evaluation",
        "collect_independent_holdout","review_cost_sensitivity"}
PROMPT=("Review the supplied research-only aggregate model metrics. "
        "Do not recommend assets, orders, position sizes, model promotion or production configuration. "
        "Static models and delayed prequential River metrics are not directly comparable. "
        "Quote-derived labels are not fills. Return only JSON matching the response_contract. "
        "Choose only allowed finding and check codes; no free text.")

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def count(v):
    if type(v) is not int or not 0<=v<=1500:raise ValueError("Invalid sample count")
    return v

def number(v,maximum):
    if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=maximum:
        raise ValueError("Invalid metric")
    return round(v,6)

def prepare(report):
    if not isinstance(report,dict) or report.get("research_only") is not True:
        raise ValueError("Research report required")
    if any(report.get(k) is not False for k in ("training_allowed","model_promoted","model_saved","weights_updated","real_orders","security_verified","live_data_verified","pilot_applied","independent_holdout_verified")):
        raise ValueError("Unexpected experiment flags")
    status=report.get("status")
    if status not in ("experiment_blocked","experiment_complete","experiment_partial"):
        raise ValueError("Invalid experiment status")
    blockers=report.get("blockers")
    if not isinstance(blockers,list) or any(not isinstance(b,str) or b not in BLOCKERS for b in blockers):
        raise ValueError("Unexpected blocker")
    rows=report.get("results")
    if not isinstance(rows,list) or len(rows)>len(MODELS):raise ValueError("Invalid results")
    results=[];seen=set()
    for row in rows:
        model=row["model"]
        if model not in MODELS or model in seen:raise ValueError("Invalid model")
        seen.add(model)
        m=row["later_window"];n=count(m["samples"])
        cm={k:count(m[k]) for k in ("true_positive","true_negative","false_positive","false_negative")}
        if n==0 or sum(cm.values())!=n:raise ValueError("Invalid confusion matrix")
        results.append({"model":model,"evaluation_mode":"delayed_prequential" if model=="river_logistic" else "fixed_earlier_window_fit",
                        "samples":n,**cm,"accuracy":number(m["accuracy"],1),
                        "balanced_accuracy":number(m["balanced_accuracy"],1),
                        "brier_score":number(m["brier_score"],1),"log_loss":number(m["log_loss"],30)})
    if status=="experiment_blocked" and results:raise ValueError("Blocked experiment has results")
    if status!="experiment_blocked" and (blockers or not {"constant_training_prior","logistic_baseline"}<=seen):
        raise ValueError("Incomplete experiment metadata")
    body={"experiment_status":status,"blockers":sorted(set(blockers)),
          "models":sorted(results,key=lambda r:r["model"]),
          "quote_labels_are_real_fills":False,"independent_holdout_verified":False,
          "model_promotion_allowed":False}
    packet_id=digest(body)
    return {"status":"manual_review_packet_ready","packet_id":packet_id,"summary":body,
            "instructions":PROMPT,"response_contract":{"packet_id":packet_id,
              "findings":"array of allowed_findings codes","next_checks":"array of allowed_checks codes"},
            "allowed_findings":sorted(FINDINGS),"allowed_checks":sorted(CHECKS),
            "api_called":False,"network_requests":False,"research_only":True,**FALSE_FLAGS}

def validate(packet,response):
    if packet.get("packet_id")!=digest(packet["summary"]):raise ValueError("Packet integrity mismatch")
    if not isinstance(response,dict) or set(response)!={"packet_id","findings","next_checks"}:
        raise ValueError("Unexpected review fields")
    if response["packet_id"]!=packet["packet_id"]:raise ValueError("Wrong review packet")
    out={}
    for field,allowed in (("findings",FINDINGS),("next_checks",CHECKS)):
        values=response[field]
        if not isinstance(values,list) or len(values)>len(allowed) or any(not isinstance(v,str) or v not in allowed for v in values) or len(set(values))!=len(values):
            raise ValueError("Invalid review codes")
        out[field]=sorted(values)
    return {"status":"external_review_codes_accepted","packet_id":packet["packet_id"],**out,
            "external_review_author_verified":False,"review_is_ground_truth":False,
            "configuration_changed":False,"training_allowed":False,"model_promoted":False,
            "api_called":False,"network_requests":False,"research_only":True,**FALSE_FLAGS}

def load(path):
    with Path(path).open("rb") as f:data=f.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError("Oversized report")
    return json.loads(data.decode("utf-8-sig"))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--experiment-report",required=True)
    p.add_argument("--response")
    a=p.parse_args()
    try:
        packet=prepare(load(a.experiment_report))
        result=validate(packet,load(a.response)) if a.response else packet
        print(json.dumps(result,indent=2,allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,OSError) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,"api_called":False,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
