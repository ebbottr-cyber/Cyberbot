"""Explicit offline DexTerm research experiment; never promotes a model."""
import argparse
import json
import os
import sqlite3
from pathlib import Path
from cyberbot.db_paths import checked
from tools.dexterm_paper_replay import collect
from tools.dexterm_exit_history import collect_exits
from tools.dexterm_learning_dataset import build
from tools.dexterm_model_experiment import evaluate
from tools.dexterm_model_history import archive


def run(*, enabled=False, allow_experiment=False, lightgbm=False, river=False, adaptive=False):
    base={"research_only":True,"real_orders":False,"model_promoted":False,"weights_updated":False}
    if enabled is not True:
        return {**base,"status":"disabled"}
    if os.getenv("CYBERBOT_PILOT_KILL_SWITCH")!="1" or os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise ValueError("Research permissions required")
    source=os.getenv("CYBERBOT_DEXTERM_ARCHIVE")
    target=os.getenv("CYBERBOT_DEXTERM_MODEL_HISTORY")
    if not source or not target:
        raise ValueError("Separate configured research archive and model history required")
    checked()
    source=Path(source).resolve(strict=True);target=Path(target).resolve()
    if not target.parent.is_dir():
        raise ValueError("Model history parent directory missing")
    rows,stats=collect(source,500)
    exits,exit_stats=collect_exits(source,rows,500)
    ds=dict(build(rows,exit_quotes=exits),**stats,**exit_stats)
    exp=evaluate(ds,allow_experiment=allow_experiment,include_lightgbm=lightgbm,include_river=river,include_adaptive=adaptive)
    # Persist aggregate experiment evidence only, including blocked evaluations.
    saved=archive(target,exp)
    return {**base,"status":exp["status"],"example_count":ds["example_count"],
            "partitions":ds["partitions"],"blockers":exp["blockers"],
            "experimental_fit_performed":exp["experimental_fit_performed"],
            "history_status":saved["status"]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--enable",action="store_true")
    p.add_argument("--allow-experiment",action="store_true")
    p.add_argument("--lightgbm",action="store_true")
    p.add_argument("--river",action="store_true")
    p.add_argument("--adaptive",action="store_true")
    a=p.parse_args()
    try:
        print(json.dumps(run(enabled=a.enable,allow_experiment=a.allow_experiment,lightgbm=a.lightgbm,river=a.river,adaptive=a.adaptive),allow_nan=False))
        return 0
    except (OSError,ValueError,TypeError,KeyError,ArithmeticError,sqlite3.Error) as exc:
        print(json.dumps({"status":"rejected","error_type":type(exc).__name__,"real_orders":False}))
        return 1

if __name__=="__main__":raise SystemExit(main())
