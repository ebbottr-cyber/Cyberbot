"""Synthetic advisory gate checks; never use live trading data."""
from datetime import datetime,timedelta,timezone
import unittest
from tools.local_research.ai_risk_referee import assess,SCOPE


class RiskRefereeTests(unittest.TestCase):
    now=datetime(2026,1,1,12,tzinfo=timezone.utc)

    def packet(self):
        stamp=self.now.isoformat()
        return {"real_orders":False,"automatic_promotion":False,"paper_readiness_verified":False,
                "model_referee":{"scope":SCOPE,"status":"REVIEW_ONLY","review_candidate":"chronos",
                    "real_orders":False,"automatic_promotion":False,"active_model_changed":False,
                    "prospective_validation_required":True,"retrospective_comparison_only":True},
                "forecast_quality":{"status":"DESCRIPTIVE_ONLY","quality_score":75,
                    "last_forecast_utc":stamp,"calibrated_probability":False,
                    "automatic_action":False,"real_orders":False},
                "forward_performance_history":{"scope":SCOPE,"status":"RESEARCH_MEASURED",
                    "rejected_records":0},
                "model_review_history":{"chronos_degradation":{"status":"NO_THRESHOLD_BREACH",
                    "automatic_action":False}},
                "journal_capacity":{"status":"BELOW_LIMIT","automatic_deletion":False},
                "windows_health":{"status":"SCHEDULER_OK","sample_is_current":True,
                    "sampled_at_utc":stamp}}

    def test_all_checks_only_human_review(self):
        r=assess(self.packet(),now=self.now)
        self.assertEqual(r["status"],"HUMAN_REVIEW_ONLY")
        self.assertEqual(r["review_candidate"],"chronos")
        self.assertFalse(r["paper_readiness_verified"])
        self.assertFalse(r["execution_risk_verified"])
        self.assertFalse(r["real_orders"])

    def test_missing_packet_fails_closed(self):
        self.assertEqual(assess({},now=self.now)["status"],"REVIEW_BLOCKED")

    def test_low_quality_and_missing_drift(self):
        p=self.packet()
        p["forecast_quality"]["quality_score"]=59
        p["model_review_history"]["chronos_degradation"]["status"]="INSUFFICIENT_EVIDENCE"
        r=assess(p,now=self.now)
        self.assertEqual(r["status"],"REVIEW_BLOCKED")
        self.assertIsNone(r["review_candidate"])
        self.assertIn("forecast_quality",r["failed_checks"])
        self.assertIn("degradation_review",r["failed_checks"])

    def test_stale_forecast_and_watchdog(self):
        r=assess(self.packet(),now=self.now+timedelta(seconds=901))
        self.assertIn("forecast_freshness",r["failed_checks"])
        self.assertIn("scheduler_health",r["failed_checks"])

    def test_capacity_and_safety_flags(self):
        p=self.packet()
        p["journal_capacity"]["status"]="LIMIT_REACHED"
        p["real_orders"]=True
        r=assess(p,now=self.now)
        self.assertIn("journal_capacity",r["failed_checks"])
        self.assertIn("research_only_flags",r["failed_checks"])
        self.assertIsNone(r["review_candidate"])

    def test_mismatched_scope_and_unknown_candidate(self):
        p=self.packet()
        p["model_referee"]["scope"]="OTHER"
        p["model_referee"]["review_candidate"]="ensemble"
        r=assess(p,now=self.now)
        self.assertIn("scope_match",r["failed_checks"])
        self.assertIn("candidate_evidence",r["failed_checks"])

    def test_future_timestamp_and_boolean_score(self):
        p=self.packet()
        p["forecast_quality"]["last_forecast_utc"]=(self.now+timedelta(seconds=1)).isoformat()
        p["forecast_quality"]["quality_score"]=True
        r=assess(p,now=self.now)
        self.assertIn("forecast_freshness",r["failed_checks"])
        self.assertIn("forecast_quality",r["failed_checks"])
