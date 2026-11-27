"""Synthetic tests: no live models, orders, or external data."""
from datetime import datetime,timedelta,timezone
import unittest
from tools.local_research.ai_model_referee import assess


class ModelRefereeTests(unittest.TestCase):
    now=datetime(2026,1,20,12,tzinfo=timezone.utc)

    def report(self):
        first=self.now-timedelta(days=5)
        last=self.now-timedelta(days=1)
        return {"version":"paired-ai-review-1",
                "comparison_protocol":"same_targets_frozen_batch_online_replay",
                "evidence_status":"EXPLORATORY_UNVERIFIED",
                "market":"FUTURES","symbol":"BTCUSDT","source":"binance-usdm-public",
                "interval":"1m","live_prediction_verified":False,
                "automatic_promotion":False,"profitability_verified":False,"real_orders":False,
                "status":"RESEARCH_MEASURED","train_samples":120,"test_samples":80,"holdout_days":5,
                "first_target_minute":int(first.timestamp()//60),
                "last_target_minute":int(last.timestamp()//60),
                "created_at":self.now.isoformat(),
                "daily_weighted_mae_pct":{"naive":.20,"mean":.18,"ar1":.16,
                                          "chronos":.12,"lightgbm":.14,"river":.15}}

    def test_review_only_candidate(self):
        r=assess(self.report(),now=self.now)
        self.assertEqual(r["status"],"REVIEW_ONLY")
        self.assertEqual(r["review_candidate"],"chronos")
        self.assertAlmostEqual(r["relative_gain_vs_reference_pct"],25)
        self.assertFalse(r["active_model_changed"])
        self.assertFalse(r["real_orders"])

    def test_insufficient_data(self):
        p=self.report()
        p["test_samples"]=59
        self.assertEqual(assess(p,now=self.now)["status"],"INSUFFICIENT_EVIDENCE")

    def test_best_baseline_not_just_naive(self):
        p=self.report()
        p["daily_weighted_mae_pct"]["ar1"]=.1
        self.assertEqual(assess(p,now=self.now)["status"],"NO_BASELINE_ADVANTAGE")

    def test_near_tie(self):
        p=self.report()
        p["daily_weighted_mae_pct"]["lightgbm"]=.121
        self.assertEqual(assess(p,now=self.now)["status"],"NO_CLEAR_LEADER")

    def test_stale(self):
        self.assertEqual(assess(self.report(),now=self.now+timedelta(days=8))["status"],"STALE_EVIDENCE")

    def test_degradation_blocks_candidate(self):
        r=assess(self.report(),now=self.now,degradation_status="REVIEW_DEGRADATION")
        self.assertEqual(r["status"],"DEPENDENCY_REVIEW_REQUIRED")
        self.assertIsNone(r["review_candidate"])

    def test_invalid_scope_and_metrics(self):
        p=self.report()
        p["symbol"]="OTHER"
        self.assertEqual(assess(p,now=self.now)["status"],"DATA_REVIEW_REQUIRED")
        p=self.report()
        p["daily_weighted_mae_pct"]["river"]=float("nan")
        self.assertEqual(assess(p,now=self.now)["status"],"DATA_REVIEW_REQUIRED")
