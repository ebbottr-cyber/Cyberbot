"""Offline orchestration tests: no exchange access or model dependencies."""
import os,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import futures_live_research as live,futures_ai_memory as memory

NOW=datetime(2026,11,27,6,40,tzinfo=timezone.utc)
SYM="BTCUSDT"
ENV={**{k:"1" for k in live.FLAGS},"CYBERBOT_BINANCE_OBSERVED_ENABLED":"1",
     "CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1","CYBERBOT_FUTURES_LIVE_PAPER_OBSERVE_ENABLED":"1",
     "CYBERBOT_FUTURES_DYNAMIC_RISK_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":SYM}
def rows(n=1200):
    return [{"at":(NOW-timedelta(minutes=n-i-1)).isoformat(),"symbol":SYM,"source":"binance-usdm-public",
             "mid":100+i*.01,"spread_bps":1,"funding_rate":.0001,"mark_index_basis_pct":.01,
             "open_interest":500+i,"book_imbalance":.2,"taker_imbalance":.1,
             "atr_1m_pct":.2,"atr_5m_pct":.5} for i in range(n)]
def snapshot(end=None,quarantine=False):
    states={k:{**memory.initial(),"runs":1,"last_end":end} for k in memory.MODELS}
    if quarantine:states["lightgbm"]["status"]="quarantined"
    return {"version":memory.VERSION,"symbol":SYM,"data_mode":"local_observations_unverified","states":states}

class LiveResearchTests(unittest.TestCase):
    def setUp(self):
        p=patch.dict(os.environ,ENV);p.start();self.addCleanup(p.stop)
    def test_wait_for_data_or_new_window(self):
        with patch.object(live.ai,"run",side_effect=AssertionError("should not train")),patch.object(live.training,"recent",return_value=rows(240)):
            self.assertEqual(live.evaluate_session(SYM,clock=lambda:NOW)["status"],"waiting_for_contiguous_data")
        with patch.object(live.ai,"run",side_effect=AssertionError("should not train")),patch.object(live.training,"recent",return_value=rows()),patch.object(live.memory,"snapshot",return_value=snapshot(NOW.isoformat())):
            self.assertEqual(live.evaluate_session(SYM,clock=lambda:NOW)["status"],"waiting_for_new_test_window")
        with patch.object(live.training,"recent",return_value=rows()):
            self.assertEqual(live.evaluate_session(SYM,clock=lambda:NOW+timedelta(minutes=3))["status"],"stale_training_data")
    def test_prior_memory_then_commit_then_veto(self):
        old=snapshot();new=snapshot(NOW.isoformat(),True)
        with patch.object(live.training,"recent",return_value=rows()),patch.object(live.memory,"snapshot",side_effect=[old,new]),patch.object(live.ai,"run",return_value={"fixture":True}),patch.object(live.memory,"compact"),patch.object(live.optimizer,"evaluate",return_value={"next_research_candidate":"lightgbm"}) as opt,patch.object(live.memory,"record",return_value={"recorded":True}),patch.object(live.ai,"gemini_review",side_effect=AssertionError("unexpected external call")),patch.object(live.pilot,"request",side_effect=AssertionError("order request")):
            out=live.evaluate_session(SYM,clock=lambda:NOW)
            self.assertIs(opt.call_args.kwargs["prior_memory"],old)
            self.assertEqual(out["status"],"research_completed")
            self.assertEqual(out["next_research_candidate"],"cash")
            self.assertEqual(out["actual_action"],"HOLD")
            self.assertFalse(out["automatic_entry_enabled"])
            self.assertFalse(out["real_orders"])
    def test_duplicate_commit_no_external_review(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_GEMINI_ENABLED":"1","CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED":"1"}),patch.object(live.training,"recent",return_value=rows()),patch.object(live.memory,"snapshot",return_value=snapshot()),patch.object(live.ai,"run",return_value={}),patch.object(live.memory,"compact"),patch.object(live.optimizer,"evaluate",return_value={}),patch.object(live.memory,"record",return_value={"recorded":False}),patch.object(live.ai,"gemini_review",side_effect=AssertionError("duplicate review")):
            self.assertEqual(live.evaluate_session(SYM,clock=lambda:NOW,include_gemini=True)["status"],"concurrent_or_overlapping_evidence")
    def test_collection_runs_only_on_new_observations(self):
        with patch.object(live.training,"run",return_value={"results":[{"status":"missed"}]}),patch.object(live,"evaluate_session",side_effect=AssertionError("no new data")):
            self.assertEqual(live.collect_session(SYM,1,clock=lambda:NOW)["status"],"no_new_observations")
        with patch.object(live.training,"run",return_value={"results":[{"status":"recorded"}]}),patch.object(live,"evaluate_session",return_value={"status":"waiting_for_contiguous_data"}) as evaluate:
            self.assertEqual(live.collect_session(SYM,1,clock=lambda:NOW)["status"],"waiting_for_contiguous_data")
            evaluate.assert_called_once()
    def test_paper_probe_separate_explicit_permission(self):
        with patch.object(live.binance,"run",return_value={"applied":True,"real_orders":False,"ingress":{"status":"observation"}}) as observe,patch.object(live.pilot,"snapshot",return_value={}),patch.object(live.pilot,"request",side_effect=AssertionError("new intent")),patch.object(live.risk,"run",side_effect=ValueError("unavailable")):
            d=live.paper_probe(SYM,clock=lambda:NOW,include_risk=True)
            self.assertTrue(observe.call_args.kwargs["apply"])
            self.assertEqual(d["risk"]["status"],"unavailable")
            self.assertFalse(d["real_orders"])
            with self.assertRaises(ValueError):live.paper_probe("ETHUSDT",clock=lambda:NOW)
            with patch.dict(os.environ,{"CYBERBOT_FUTURES_LIVE_PAPER_OBSERVE_ENABLED":"0"}):
                with self.assertRaises(ValueError):live.paper_probe(SYM,clock=lambda:NOW)
            self.assertEqual(observe.call_count,1)
    def test_disabled_before_io(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_LIVE_RESEARCH_ENABLED":"0"}),patch.object(live.training,"recent",side_effect=AssertionError("disabled")),patch.object(live.training,"run",side_effect=AssertionError("disabled")):
            with self.assertRaises(ValueError):live.evaluate_session(SYM)
            with self.assertRaises(ValueError):live.collect_session(SYM,1)
