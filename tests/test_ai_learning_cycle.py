"""Synthetic advisory learning cycle tests; no native ML, orders, or I/O."""
from datetime import datetime,timedelta,timezone
import unittest
from tools.local_research.ai_learning_cycle import plan,SCOPE


class LearningCycleTests(unittest.TestCase):
    now=datetime(2026,1,20,12,tzinfo=timezone.utc)

    def rows(self):
        t=self.now-timedelta(days=15)
        items=[(int((t+timedelta(days=d,minutes=22*i)).timestamp()//60),
                (t+timedelta(days=d)).date().isoformat())
               for d in range(15) for i in range(15)]
        return items[:150],items[150:]

    def packet(self,previous=False):
        result={"real_orders":False,"automatic_promotion":False,
                "error_memory":{"scope":SCOPE,"status":"RESEARCH_MEASURED",
                    "measured_records":225,"unmeasurable_records":{},"rejected_records":0,
                    "groups":[{"regime":"all","status":"DESCRIPTIVE_ONLY",
                        "models":{"chronos":{"rates_pct":{"worse_than_zero_return":45}}}}]},
                "forward_performance_history":{"scope":SCOPE,"status":"RESEARCH_MEASURED","rejected_records":0},
                "model_referee":{"scope":SCOPE,"status":"NOT_AVAILABLE"},
                "model_review_history":{"chronos_degradation":{"status":"REVIEW_DEGRADATION"}},
                "journal_capacity":{"status":"BELOW_LIMIT"}}
        if previous:
            result["model_referee"].update(status="DEPENDENCY_REVIEW_REQUIRED",
                last_target_utc=(self.now-timedelta(days=4)).isoformat(),
                report_created_at_utc=(self.now-timedelta(days=3)).isoformat())
        return result

    def test_initial_comparison_only(self):
        result=plan(self.packet(),*self.rows(),now=self.now)
        self.assertEqual(result["status"],"INITIAL_COMPARISON_REVIEW")
        self.assertFalse(result["training_started"])
        self.assertFalse(result["chronos_weights_updated"])
        self.assertFalse(result["real_orders"])

    def test_new_evidence_and_degradation(self):
        result=plan(self.packet(True),*self.rows(),now=self.now)
        self.assertEqual(result["status"],"RECOMPARISON_REVIEW")
        self.assertGreaterEqual(result["new_retained_blocks"],30)
        self.assertIn("CHRONOS_DEGRADATION_REVIEW",result["reasons"])

    def test_cooldown(self):
        p=self.packet(True)
        p["model_referee"]["report_created_at_utc"]=self.now.isoformat()
        self.assertEqual(plan(p,*self.rows(),now=self.now)["status"],"WAIT_COOLDOWN")

    def test_no_new_data(self):
        p=self.packet(True)
        p["model_referee"]["last_target_utc"]=(self.now-timedelta(hours=12)).isoformat()
        p["model_referee"]["report_created_at_utc"]=self.now.isoformat()
        self.assertEqual(plan(p,*self.rows(),now=self.now)["status"],"WAIT_NEW_DATA")

    def test_bad_data_and_storage(self):
        p=self.packet()
        p["error_memory"]["unmeasurable_records"]={"missing_target_sample":30}
        self.assertEqual(plan(p,*self.rows(),now=self.now)["status"],"DATA_REVIEW_REQUIRED")
        p=self.packet()
        p["journal_capacity"]["status"]="LIMIT_REACHED"
        self.assertEqual(plan(p,*self.rows(),now=self.now)["status"],"WAIT_STORAGE")

    def test_insufficient_samples(self):
        self.assertEqual(plan(self.packet(),[],[],now=self.now)["status"],"WAIT_EVIDENCE")
