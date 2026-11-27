"""One bounded research learning cycle; default offline, no scheduler or deployment."""
import argparse
import json
import sqlite3
from pathlib import Path
from tools.solana_paper_replay import collect,FALSE_FLAGS
from tools.solana_learning_readiness import evaluate as readiness
from tools.solana_learning_dataset import build
from tools.solana_model_experiment import evaluate as experiment
from tools.solana_model_history import archive
from tools.solana_gemini_review import prepare as review_packet
from tools.dexterm_research_cycle import permissions

def run(database,history_database,*,limit=500,allow_experiment=False,
        include_lightgbm=False,include_river=False,include_adaptive=False,
        dexterm_root=None,report_dir=None):
    for v in (allow_experiment,include_lightgbm,include_river,include_adaptive):
        if type(v) is not bool:raise ValueError("Explicit boolean options required")
    if type(limit) is not int or not 1<=limit<=500:raise ValueError("Invalid archive limit")
    source=Path(database).resolve();target=Path(history_database).resolve()
    if source==target or (source.exists() and target.exists() and source.samefile(target)):
        raise ValueError("Research and model history databases must be separate")
    if (dexterm_root is None)!=(report_dir is None):
        raise ValueError("Collection requires both root and report directory")
    result={"status":"learning_cycle_partial","stage":"collection","research_only":True,
            "collection_requested":dexterm_root is not None,"collection":None,
            "production_training_performed":False,"training_allowed":False,
            "weights_updated":False,"model_promoted":False,"model_saved":False,
            "scheduled":False,"gemini_api_called":False,**FALSE_FLAGS}
    if dexterm_root is not None:
        permissions()
        # Only one bounded foreground collection; no retries here.
        from tools.dexterm_research_cycle import run as collect_cycle
        collected=collect_cycle(dexterm_root,source,report_dir,cycles=1)
        result["collection"]=collected
        if collected["status"]!="research_run_complete":
            result["stop_reason"]="collection_partial"
            return result
    # All downstream stages use the same immutable in-memory observation set.
    result["stage"]="archive_read"
    rows,stats=collect(source,limit)
    result["archive_stats"]=stats
    result["stage"]="readiness"
    r=readiness(rows)
    result["readiness"]=r
    result["stage"]="dataset"
    ds=dict(build(rows),**stats)
    result["dataset"]={k:ds[k] for k in ("status","dataset_sha256","example_count","partitions","skipped","split_timestamp")}
    result["stage"]="experiment"
    e=experiment(ds,allow_experiment=allow_experiment,include_lightgbm=include_lightgbm,
                 include_river=include_river,include_adaptive=include_adaptive)
    result["experiment"]=e
    result["stage"]="review_packet"
    result["manual_review_packet"]=review_packet(e)
    result["stage"]="model_history"
    result["history_write"]=archive(target,e)
    result["stage"]="complete"
    result["status"]="learning_cycle_complete" if e["status"]!="experiment_partial" else "learning_cycle_partial"
    result["experiment_blocked"]=e["status"]=="experiment_blocked"
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--history-database",required=True)
    p.add_argument("--limit",type=int,default=500)
    p.add_argument("--allow-experiment",action="store_true")
    p.add_argument("--include-lightgbm",action="store_true")
    p.add_argument("--include-river",action="store_true")
    p.add_argument("--include-adaptive",action="store_true")
    p.add_argument("--dexterm-root")
    p.add_argument("--report-dir")
    a=p.parse_args()
    try:
        d=run(a.database,a.history_database,limit=a.limit,allow_experiment=a.allow_experiment,
              include_lightgbm=a.include_lightgbm,include_river=a.include_river,
              include_adaptive=a.include_adaptive,dexterm_root=a.dexterm_root,report_dir=a.report_dir)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"]=="learning_cycle_complete" else 2
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,"training_allowed":False,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
