"""Fail-closed advisory review gate, not an execution risk engine.

Consumes read-only diagnostics from the local dashboard. A successful packet
only permits human review of a retrospective candidate. Diagnostics are not
an atomic snapshot and do not establish order or paper readiness.
"""
from datetime import datetime, timezone

from .adaptive_review import utc

MIN_QUALITY=60
MAX_FORECAST_AGE=60
MAX_HEALTH_AGE=900
SCOPE="FUTURES/BTCUSDT/binance-usdm-public"
CANDIDATES=("chronos","river","lightgbm")


def assess(snapshot, *, now=None):
    now=now or datetime.now(timezone.utc)
    reasons=[]
    checks={}
    def check(name, passed):
        checks[name]=bool(passed)
        if not passed:
            reasons.append(name)

    candidate=None
    try:
        referee=snapshot["model_referee"]
        quality=snapshot["forecast_quality"]
        history=snapshot["forward_performance_history"]
        drift=snapshot["model_review_history"]["chronos_degradation"]
        storage=snapshot["journal_capacity"]
        health=snapshot["windows_health"]

        check("research_only_flags", snapshot["real_orders"] is False
              and snapshot["automatic_promotion"] is False
              and snapshot["paper_readiness_verified"] is False
              and referee["real_orders"] is False
              and referee["automatic_promotion"] is False
              and referee["active_model_changed"] is False
              and referee["prospective_validation_required"] is True)
        check("scope_match",referee["scope"]==SCOPE and history["scope"]==SCOPE)
        check("candidate_evidence",referee["status"]=="REVIEW_ONLY"
              and referee["review_candidate"] in CANDIDATES
              and referee.get("retrospective_comparison_only") is True)
        check("forward_evidence",history["status"]=="RESEARCH_MEASURED"
              and history.get("rejected_records")==0)
        check("degradation_review",drift["status"]=="NO_THRESHOLD_BREACH"
              and drift["automatic_action"] is False)
        score=quality.get("quality_score")
        check("forecast_quality",quality["status"]=="DESCRIPTIVE_ONLY"
              and type(score) is int and MIN_QUALITY<=score<=100
              and quality["calibrated_probability"] is False
              and quality["automatic_action"] is False
              and quality["real_orders"] is False)
        stamp=quality.get("last_forecast_utc")
        check("forecast_freshness",stamp is not None
              and 0<=(now-utc(stamp)).total_seconds()<=MAX_FORECAST_AGE)
        check("journal_capacity",storage["status"]=="BELOW_LIMIT"
              and storage["automatic_deletion"] is False)
        sampled=health.get("sampled_at_utc")
        check("scheduler_health",health["status"]=="SCHEDULER_OK"
              and health.get("sample_is_current") is True
              and sampled is not None
              and -5<=(now-utc(sampled)).total_seconds()<=MAX_HEALTH_AGE)
        if not reasons:
            candidate=referee["review_candidate"]
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
        reasons.append("invalid_or_missing_diagnostics")
    return {"version":"ai-risk-referee-1","scope":SCOPE,
            "status":"HUMAN_REVIEW_ONLY" if not reasons else "REVIEW_BLOCKED",
            "review_candidate":candidate,"failed_checks":reasons,"checks":checks,
            "min_heuristic_quality_score":MIN_QUALITY,
            "quality_is_chronos_reference_diagnostic":True,
            "three_ai_agreement_verified":False,
            "cross_source_atomic_snapshot":False,
            "execution_risk_verified":False,"paper_readiness_verified":False,
            "automatic_promotion":False,"real_orders":False}
