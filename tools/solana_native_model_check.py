"""Opt-in native model compatibility check with synthetic data only; no saved weights."""
import argparse
import hashlib
import json
import os
import socket
from contextlib import ExitStack
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from tools.solana_learning_dataset import FEATURE_NAMES
from tools.solana_model_experiment import evaluate
from tools.solana_gemini_review import prepare
from tools.solana_model_history import normalize
from tools.solana_paper_replay import FALSE_FLAGS

def fixture():
    base=datetime(2026,1,1,tzinfo=timezone.utc)
    cut=base+timedelta(hours=12)
    rows=[]
    for part,n,start in (("earlier",120,base),("later",60,cut)):
        for i in range(n):
            feature_at=start+timedelta(seconds=240*i)
            positive=i%2==0
            rows.append({"mint":"synthetic-"+str(i%6),"partition":part,
                         "feature_at":feature_at.isoformat(),
                         "label_at":(feature_at+timedelta(seconds=180)).isoformat(),
                         "features":dict(zip(FEATURE_NAMES,(100000000,100 if positive else -100,(i%7)-3,240))),
                         "label":{"positive_quote_net":positive}})
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {"source_scope":"dexterm_bridge_only","research_only":True,
            "training_allowed":False,"training_performed":False,"model_promoted":False,
            "real_orders":False,"labels_are_real_fills":False,
            "feature_names":list(FEATURE_NAMES),"examples":rows,"example_count":len(rows),
            "dataset_sha256":digest,"split_timestamp":cut.isoformat()}

def denied(*args,**kwargs):
    raise RuntimeError("Network disabled in native model check")

def run(*,enabled=False):
    if enabled is not True:raise ValueError("Explicit synthetic fit permission required")
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("CYBERBOT_","DEXTERM_","HELIUS_","JUPITER_"))}
    env.update(CYBERBOT_PILOT_KILL_SWITCH="1",CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED="0",
               OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",NUMEXPR_NUM_THREADS="1")
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ,env,clear=True))
        for name in ("connect","connect_ex","sendto","sendall"):
            stack.enter_context(patch.object(socket.socket,name,denied))
        for name in ("create_connection","getaddrinfo"):
            stack.enter_context(patch.object(socket,name,denied))
        report=evaluate(fixture(),allow_experiment=True,include_lightgbm=True,
                        include_river=True,include_adaptive=True)
        packet=prepare(report)
        normalized=normalize(report)
    results={r["model"]:r for r in report["results"]}
    checks={"logistic_regression":report["experimental_fit_performed"] is True and "logistic_baseline" in results,
            "lightgbm":report["lightgbm_status"]=="experiment_complete" and "lightgbm" in results,
            "river":report["river_status"]=="experiment_complete" and "river_logistic" in results,
            "consensus":report["consensus"]["status"]=="consensus_diagnostic_complete",
            "adaptive":report["adaptive_weights"]["status"]=="adaptive_weights_diagnostic_complete" and
                       report["adaptive_weights"]["adaptive_samples"]>0,
            "manual_review_packet":packet["status"]=="manual_review_packet_ready",
            "model_history_schema":normalized["schema_version"]==1}
    ok=report["status"]=="experiment_complete" and all(checks.values())
    return {"status":"native_check_passed" if ok else "native_check_incomplete","synthetic_only":True,
            "checks":checks,"optional_status":{"lightgbm":report["lightgbm_status"],"river":report["river_status"]},
            "versions":{k:results[k]["version"] for k in ("lightgbm","river_logistic") if k in results},
            "native_optional_model_fit_verified":checks["lightgbm"] and checks["river"],
            "live_provider_verified":False,"model_saved":False,"model_promoted":False,
            "weights_updated":False,"production_training_performed":False,
            "performance_improvement_verified":False,"gemini_api_called":False,**FALSE_FLAGS}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-synthetic-fit",action="store_true")
    a=p.parse_args()
    try:
        result=run(enabled=a.allow_synthetic_fit)
        print(json.dumps(result,indent=2,allow_nan=False))
        return 0 if result["status"]=="native_check_passed" else 2
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,RuntimeError,OSError,ImportError) as e:
        print(json.dumps({"status":"native_check_rejected","error_type":type(e).__name__,
                          "native_optional_model_fit_verified":False,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
