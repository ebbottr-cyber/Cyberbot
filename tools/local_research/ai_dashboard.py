"""Read-only dashboard handoff: research inventory and recent Windows task health.

No routes are registered here. A future authenticated panel can consume snapshot().
Host resources are sampled, not process-level usage or a readiness guarantee.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from . import ai_status, journal_capacity, ai_performance_history, ai_review_history, ai_model_referee, ai_forecast_quality, ai_regime_review, ai_risk_referee, ai_decision_memory

TASKS = {"Chronos", "RiverLive", "RiverReplay", "LightGBM", "ForwardBackup"}
TASK_STATES = {"NOT_REGISTERED", "DISABLED", "NOT_RUN", "RUNNING", "EXIT_OK",
               "FAILED", "DEFERRED", "STALE", "STALE_DEFERRED", "REVIEW_REQUIRED",
               "OVERRUN_REVIEW_REQUIRED", "CLOCK_REVIEW_REQUIRED"}
HEALTH_STATES = {"REVIEW_REQUIRED", "NOT_FULLY_RUNNING", "SCHEDULER_OK"}
MAX_BYTES = 2 * 1024 * 1024
MAX_AGE_SECONDS = 900


def resource_summary(value):
    if value is None:
        return None
    keys = ("free_ram_bytes", "total_ram_bytes", "free_disk_bytes", "total_disk_bytes")
    if not isinstance(value, dict) or value.get("scope") != "host_sample_not_process_usage":
        raise ValueError("invalid resource sample")
    if any(type(value.get(k)) is not int or not 0 <= value[k] <= 2**63-1 for k in keys):
        raise ValueError("invalid resource size")
    for kind in ("ram", "disk"):
        if not 0 < value["total_"+kind+"_bytes"] or value["free_"+kind+"_bytes"] > value["total_"+kind+"_bytes"]:
            raise ValueError("inconsistent resource size")
    return {**{k:value[k] for k in keys}, "scope":"host_sample_not_process_usage"}


def windows_health(root, now=None):
    now = now or datetime.now(timezone.utc)
    path = root / "var/ai-health/watchdog-history.json"
    try:
        if not path.is_file():
            return {"status":"NOT_AVAILABLE","tasks":[],"resources":None}
        if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
            raise ValueError("unsafe health path")
        with path.open("rb") as f:
            raw = f.read(MAX_BYTES + 1)
        if len(raw)>MAX_BYTES:
            raise ValueError("health history too large")
        history = json.loads(raw)
        if not isinstance(history,list) or not 1<=len(history)<=288:
            raise ValueError("invalid history")
        report=history[-1]
        stamp=datetime.fromisoformat(report["checked_at_utc"].replace("Z","+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("missing timezone")
        age=(now-stamp).total_seconds()
        if age < -5 or report["status"] not in HEALTH_STATES or report["real_orders"] is not False or report["task_configuration_modified"] is not False:
            raise ValueError("invalid health report")
        tasks={}
        for row in report["tasks"]:
            name=row["name"]
            if not name.startswith("Cyberbot-AI-"):
                raise ValueError("unexpected task")
            key=name.removeprefix("Cyberbot-AI-")
            if key not in TASKS or key in tasks or row["status"] not in TASK_STATES:
                raise ValueError("invalid task state")
            tasks[key]={"name":key,"status":row["status"]}
        if set(tasks)!=TASKS:
            raise ValueError("incomplete task inventory")
        stale=age>MAX_AGE_SECONDS
        return {"status":"STALE" if stale else report["status"],
                "sampled_at_utc":stamp.astimezone(timezone.utc).isoformat(),
                "age_seconds":max(0,int(age)),
                "tasks":[tasks[k] for k in sorted(tasks)],
                "resources":None if stale else resource_summary(report.get("resources")),
                "sample_is_current":not stale}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return {"status":"DATA_REVIEW_REQUIRED","tasks":[],"resources":None}


def storage_summary(root):
    try:
        return journal_capacity.inventory(root)
    except (OSError, ValueError):
        return {"status":"DATA_REVIEW_REQUIRED","journals":{},"automatic_deletion":False}


def snapshot(root):
    root=Path(root).resolve()
    forward=ai_performance_history.run(root)
    reviews=ai_review_history.snapshot(root,forward)
    result={"version":"ai-dashboard-1",
            "research":ai_status.run(root),
            "windows_health":windows_health(root),
            "journal_capacity":storage_summary(root),
            "forward_performance_history":forward,
            "model_review_history":reviews,
            "model_referee":ai_model_referee.run(root,degradation_status=reviews["chronos_degradation"]["status"]),
            "forecast_quality":ai_forecast_quality.run(root),
            "regime_review":ai_regime_review.run(root),
            "paper_readiness_verified":False,
            "real_orders":False,"automatic_promotion":False,
            "cross_source_atomic_snapshot":False}
    result["risk_referee"]=ai_risk_referee.assess(result)
    result["decision_memory"]=ai_decision_memory.history(root)
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    print(json.dumps(snapshot(p.parse_args().root),indent=2,allow_nan=False))
