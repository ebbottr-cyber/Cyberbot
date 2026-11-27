"""Public-to-authorized-panel projection of the local AI research snapshot.

No model execution, order entry, raw payloads, paths or credentials in this API.
"""
from pathlib import Path
from threading import Lock
from fastapi import HTTPException
from tools.local_research import ai_dashboard

ROOT=Path(__file__).resolve().parents[1]
_lock=Lock()
STATES=frozenset("""
NOT_AVAILABLE NOT_INITIALIZED AWAITING_EVIDENCE NO_REPORT NO_LOCAL_ATTEMPTS
RECORDED_NOT_REVALIDATED RESEARCH_MEASURED INSUFFICIENT_EVIDENCE
DATA_REVIEW_REQUIRED RESEARCH_ONLY BELOW_LIMIT LIMIT_REACHED AVAILABLE
REVIEW_BLOCKED HUMAN_REVIEW_ONLY REVIEW_ONLY NO_CLEAR_ADVANTAGE
WAIT_EVIDENCE WAIT_STORAGE WAIT_NEW_DATA WAIT_COOLDOWN INITIAL_COMPARISON_REVIEW
RECOMPARISON_REVIEW WAIT_LEARNING_REVIEW READY_FOR_PAIRED_RESEARCH
SCHEDULER_OK NOT_FULLY_RUNNING REVIEW_REQUIRED STALE STALE_FORECAST
NOT_REGISTERED DISABLED NOT_RUN RUNNING EXIT_OK FAILED DEFERRED STALE_DEFERRED
OVERRUN_REVIEW_REQUIRED CLOCK_REVIEW_REQUIRED OK RESERVED PROVIDER_ERROR
NO_THRESHOLD_BREACH REVIEW_DEGRADATION DESCRIPTIVE_ONLY LOW_SAMPLE
""".split())
SECTIONS=("windows_health","journal_capacity","forward_performance_history",
          "model_referee","forecast_quality","regime_review","risk_referee",
          "decision_memory","error_memory","learning_cycle","challenger_trial",
          "model_lifecycle","orchestrator")

def state(value):
    status=value.get("status") if isinstance(value,dict) else None
    return status if isinstance(status,str) and status in STATES else "UNKNOWN"

def project(report):
    if report.get("version")!="ai-dashboard-1" or any(report.get(k) is not False
            for k in ("real_orders","automatic_promotion","paper_readiness_verified")):
        raise ValueError("invalid research report")
    research=report["research"]
    if research.get("real_orders") is not False or research.get("automatic_promotion") is not False:
        raise ValueError("invalid research inventory")
    models=research["models"]
    health=report["windows_health"]
    tasks=[]
    for task in health.get("tasks",[]):
        if task["name"] in ai_dashboard.TASKS|{ai_dashboard.OPTIONAL_TASK}:
            tasks.append({"name":task["name"],"status":state(task)})
    resources=ai_dashboard.resource_summary(health.get("resources")) if health.get("sample_is_current") is True else None
    counts={}
    for key in ("pending","measured","unmeasurable"):
        v=models["chronos"].get("counts",{}).get(key)
        counts[key]=v if type(v) is int and 0<=v<=2**53-1 else None
    return {"version":"ai-panel-1","scope":"FUTURES/BTCUSDT/1m/binance-usdm-public",
            "models":{name:state(models[name]) for name in ("chronos","river","lightgbm","gemini")},
            "sections":{name:state(report[name]) for name in SECTIONS},
            "chronos_recorded_counts":counts,"tasks":tasks,"resources":resources,
            "sample_is_current":health.get("sample_is_current") is True,
            "real_orders":False,"automatic_promotion":False,
            "paper_readiness_verified":False,"cross_source_atomic_snapshot":False}

def read():
    if not _lock.acquire(blocking=False):
        raise HTTPException(429,"AI araştırma raporu zaten okunuyor.")
    try:
        return project(ai_dashboard.snapshot(ROOT))
    except Exception:
        # Do not expose exception text, local paths or raw journal contents.
        raise HTTPException(503,"AI araştırma raporu okunamadı; yerel inceleme gerekli.") from None
    finally:
        _lock.release()
