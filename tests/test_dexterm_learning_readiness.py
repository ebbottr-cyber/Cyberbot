import unittest
from datetime import datetime,timezone,timedelta
from tools.dexterm_learning_readiness import coverage,evaluate,STRESS_LEVELS

M="1"*31+"2"
N="1"*31+"3"
def row(seconds,qty=200,mint=M,index=0):
    return {"mint":mint,"timestamp":(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=seconds)).isoformat(),
            "input_raw":100000000,"token_amount_raw":qty,"return_raw":99000000,
            "source_digest":"fixture","source_index":index}

class LearningReadinessTests(unittest.TestCase):
    def test_exact_quantity_and_censoring(self):
        d=coverage([row(0),row(180),row(3600,mint=N)])
        self.assertEqual(d["eligible_entries"],1)
        self.assertEqual(d["exact_quantity_matches"],1)
        self.assertEqual(d["right_censored_entries"],2)
        self.assertEqual(d["exact_match_pct"],100)
    def test_different_quantity_not_rescaled(self):
        d=coverage([row(0),row(180,qty=201),row(3600,mint=N)])
        self.assertEqual(d["different_quantity_only"],1)
        self.assertEqual(d["exact_quantity_matches"],0)
    def test_ambiguous_observations_excluded(self):
        d=coverage([row(0),row(0,qty=201,index=1),row(3600,mint=N)])
        self.assertEqual(d["ambiguous_observations"],2)
        self.assertEqual(d["eligible_entries"],0)
        self.assertIsNone(d["exact_match_pct"])
    def test_stress_comparison_does_not_train(self):
        d=evaluate([row(0),row(180),row(3600,mint=N)])
        self.assertEqual([s["stress_bps_per_direction"] for s in d["cost_scenarios"]],list(STRESS_LEVELS))
        self.assertIn("insufficient_comparable_policy_samples",d["blockers"])
        self.assertFalse(d["training_allowed"])
        self.assertFalse(d["weights_updated"])
        self.assertFalse(d["real_orders"])
        self.assertIsNone(d["winner"])
    def test_empty_data_is_not_training_ready(self):
        d=evaluate([])
        self.assertEqual(d["observation_count"],0)
        self.assertIsNone(d["coverage"]["full_history"]["exact_match_pct"])
        self.assertFalse(d["training_performed"])
