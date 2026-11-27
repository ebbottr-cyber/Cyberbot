import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from tools.solana_trial_assessment import run,day_metrics

BASE=datetime(2026,1,1,tzinfo=timezone.utc)
def stamp(s):return (BASE+timedelta(seconds=s)).isoformat()
def row(s,qty=200,returned=99000000,index=0):
    return {"mint":"m","timestamp":stamp(s),"input_raw":100000000,"token_amount_raw":qty,
            "return_raw":returned,"source_digest":"entry","source_index":index}

class TrialAssessmentTests(unittest.TestCase):
    def test_empty_trial_never_passes(self):
        with patch("tools.solana_trial_assessment.collect",return_value=([],{"bridge_history_truncated":False})),patch("tools.solana_trial_assessment.collect_exits",return_value=([],{"exit_history_truncated":False})):
            out=run("unused",start=stamp(0),end=stamp(7*86400),now=BASE+timedelta(days=8))
        self.assertEqual(out["status"],"trial_evidence_insufficient")
        self.assertEqual(len(out["daily"]),7)
        self.assertIsNone(out["exact_match_pct"])
        self.assertFalse(out["profitability_verified"])
        self.assertFalse(out["real_orders"])
    def test_truncated_day_and_import_time_leak(self):
        with patch("tools.solana_trial_assessment.collect",return_value=([row(86400)],{"bridge_history_truncated":True})),patch("tools.solana_trial_assessment.collect_exits",return_value=([],{"exit_history_truncated":False})):
            out=run("unused",start=stamp(0),end=stamp(86400),now=BASE+timedelta(days=2))
        self.assertIn("archive_window_truncated",out["blockers"])
        self.assertEqual(out["daily"][0]["observations_outside_day"],1)
        self.assertEqual(out["days_with_observations_in_complete_windows"],0)
    def test_cost_sensitivity_and_no_fake_equity(self):
        d=day_metrics([row(0),row(300,returned=110000000)],[])
        self.assertEqual(d["scenarios"][0]["closed_positions"],1)
        self.assertGreater(d["scenarios"][0]["realized_net_raw"],d["scenarios"][2]["realized_net_raw"])
        d=day_metrics([row(0)],[])
        self.assertIsNone(d["scenarios"][0]["final_equity_raw"])
        self.assertIsNone(d["scenarios"][0]["closed_only_profit_factor"])
    def test_boundaries_and_limit(self):
        for start,end in ((stamp(1),stamp(86400)),(stamp(0),stamp(15*86400)),(stamp(86400),stamp(0))):
            with self.assertRaises(ValueError):run("unused",start=start,end=end,now=BASE+timedelta(days=20))
        with self.assertRaises(ValueError):run("unused",start=stamp(0),end=stamp(86400),now=BASE)
