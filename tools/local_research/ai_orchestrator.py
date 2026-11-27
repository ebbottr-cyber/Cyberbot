"""Explicit local paired research coordinator; preview is read-only.

Use the Windows launcher for resource admission and mutual exclusion.
The Python module itself does not claim a system-wide lock or hard quota.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat

from .journal_capacity import safe_stat, SUFFIXES
from .vps_guard import MIB, MIN_FREE_DISK_MIB

READY={"INITIAL_COMPARISON_REVIEW","RECOMPARISON_REVIEW"}
MAX_PAIRED_BYTES=16*MIB
SCOPE="FUTURES/BTCUSDT/binance-usdm-public"


def admission(snapshot):
    base={"version":"ai-orchestrator-1","automatic_promotion":False,
          "real_orders":False,"production_activation":False,
          "training_started":False,"resource_lock_verified":False}
    try:
        cycle=snapshot["learning_cycle"]
        if (snapshot["real_orders"] is not False or snapshot["automatic_promotion"] is not False
                or cycle["scope"]!=SCOPE or cycle["training_started"] is not False
                or cycle["automatic_promotion"] is not False or cycle["real_orders"] is not False):
            raise ValueError("unexpected research state")
        if cycle["status"]=="DATA_REVIEW_REQUIRED" or snapshot["journal_capacity"]["status"]=="DATA_REVIEW_REQUIRED":
            return {**base,"status":"DATA_REVIEW_REQUIRED","learning_status":cycle["status"]}
        if cycle["status"]=="WAIT_STORAGE":
            return {**base,"status":"WAIT_STORAGE","learning_status":cycle["status"]}
        if cycle["status"] not in READY:
            return {**base,"status":"WAIT_LEARNING_REVIEW","learning_status":cycle["status"]}
        if cycle.get("next_review")!="PAIRED_LIGHTGBM_RIVER_RESEARCH":
            raise ValueError("unsupported review")
        if snapshot["journal_capacity"]["status"]!="BELOW_LIMIT":
            return {**base,"status":"WAIT_STORAGE"}
        return {**base,"status":"READY_FOR_PAIRED_RESEARCH","learning_status":cycle["status"]}
    except (KeyError,TypeError,ValueError,AttributeError):
        return {**base,"status":"DATA_REVIEW_REQUIRED"}


def check_paths(root):
    folder=Path(root)/"var/ai"
    for p in (folder.parent,folder):
        s=safe_stat(p)
        if s is None or not stat.S_ISDIR(s.st_mode):
            raise ValueError("research folder required")
    total=0
    for name in ("forward-models-v2.sqlite3","paired-ai-review.sqlite3"):
        for suffix in SUFFIXES:
            s=safe_stat(folder/(name+suffix))
            if s is None:
                if name.startswith("forward-") and not suffix:
                    raise ValueError("source journal required")
                continue
            if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:
                raise ValueError("unsafe research journal")
            if name.startswith("paired-"):
                total+=s.st_size
    return total<MAX_PAIRED_BYTES and shutil.disk_usage(folder).free>=MIN_FREE_DISK_MIB*MIB


def run(root, *, execute=False, snapshot_factory=None, paired_run=None):
    if snapshot_factory is None:
        from .ai_dashboard import snapshot as snapshot_factory
    root=Path(root).resolve()
    result=admission(snapshot_factory(root))
    if not execute or result["status"]!="READY_FOR_PAIRED_RESEARCH":
        return {**result,"executed":False}
    if os.getenv("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        return {**result,"status":"WAIT_RIGHTS","executed":False}
    if not check_paths(root):
        return {**result,"status":"WAIT_CAPACITY","executed":False}
    if paired_run is None:
        from .paired_ai_review import run as paired_run
    report=paired_run(root)
    if report.get("real_orders") is not False or report.get("automatic_promotion") is not False:
        raise ValueError("unsafe research result")
    return {**result,"status":"PAIRED_RESEARCH_COMPLETED","executed":True,
            "training_started":not report.get("cached",False) and report.get("status")=="RESEARCH_MEASURED",
            "comparison_status":report["status"],"cached":report.get("cached",False),
            "candidate_activated":False}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--execute",action="store_true",help="use only through resource-controlled launcher")
    args=p.parse_args()
    result=run(args.root,execute=args.execute)
    print(json.dumps(result,indent=2,allow_nan=False))
    if args.execute and not result["executed"]:
        raise SystemExit(75 if result["status"]!="DATA_REVIEW_REQUIRED" else 2)
