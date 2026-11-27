import os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from unittest.mock import patch
from cyberbot import futures_pilot as f,futures_auto_paper as auto
AT=datetime(2026,1,1,12,tzinfo=timezone.utc)
SYM="BTCUSDT"
class AutoPaperTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);p=Path(tmp.name)
        env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(p/"pilot.sqlite3"),
             "CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1",
             "CYBERBOT_FUTURES_PILOT_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":SYM,"CYBERBOT_PILOT_KILL_SWITCH":"0",
             "CYBERBOT_FUTURES_AUTO_PAPER_ENABLED":"1","CYBERBOT_FUTURES_AUTO_PAPER_CONFIRMED":"1","CYBERBOT_BINANCE_OBSERVED_ENABLED":"1",
             "CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_INGRESS_ENABLED":"1","CYBERBOT_INGRESS_SOURCE_FUTURES":"binance-usdm-public"}
        envpatch=patch.dict(os.environ,env);envpatch.start();self.addCleanup(envpatch.stop)
        self.now=AT+timedelta(seconds=5)
        f.observe(self.quote(),clock=self.clock)
    def clock(self):return self.now
    def quote(self,price="100"):
        return {"market":"FUTURES","symbol":SYM,"currency":"USDT","contract":"linear_perpetual","source":"binance-usdm-public",
                "source_at":self.now.isoformat(),"bid":price,"ask":str(D(price)+D(".1")),"mark":price,"bid_depth_usdt":"1000","ask_depth_usdt":"1000","funding":[]}
    def candidate(self):
        return {"version":"futures-ai-bridge-1","symbol":SYM,"status":"shadow_candidate","blockers":[],"actual_action":"HOLD","real_orders":False,"paper_orders":False,
                "research_candidate":"LONG","forecast":{"feature_at":AT.isoformat()},"valid_until":(AT+timedelta(seconds=25)).isoformat(),
                "risk_quote_reference":{"source":"binance-usdm-public","source_at":self.now.isoformat(),"mid":"100.05"},
                "risk_proposal":{"side":"LONG","stop_distance_pct":"1","target_distance_pct":"2","leverage_cap":"1",
                                 "quantity":"0.2","risk_budget_usdt":"2","funding_reserve_usdt":".04"}}
    def queue(self):return f.queue_auto(self.candidate(),gate=lambda now:True,clock=self.clock)
    def test_next_quote_fill_and_horizon_exit(self):
        self.queue();self.assertIsNone(f.snapshot(clock=self.clock)["position"])
        self.now+=timedelta(seconds=1)
        self.assertEqual(f.observe(self.quote(),clock=self.clock,auto_paper=True)["status"],"open_fill")
        pos=f.snapshot(clock=self.clock)["position"]
        self.assertEqual(pos["origin"],"ai_auto");self.assertLessEqual(D(pos["qty"]),D(".2"))
        self.assertEqual(D(pos["margin"]),D(pos["qty"])*D(pos["entry"]))
        self.now=AT+timedelta(minutes=5)
        f.observe(self.quote(),clock=self.clock)
        self.assertEqual(f.snapshot(clock=self.clock)["pending"]["reason"],"ai_horizon")
        self.now+=timedelta(seconds=1)
        self.assertEqual(f.observe(self.quote(),clock=self.clock)["status"],"close_fill")
    def test_manual_observation_cancels_auto_intent(self):
        self.queue();self.now+=timedelta(seconds=1)
        self.assertEqual(f.observe(self.quote(),clock=self.clock)["status"],"entry_cancelled")
        self.assertIsNone(f.snapshot(clock=self.clock)["position"])
        with self.assertRaises(ValueError):self.queue()
    def test_kill_switch_and_disabled_cancel(self):
        self.queue();self.now+=timedelta(seconds=1)
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_AUTO_PAPER_CONFIRMED":"0"}):
            self.assertEqual(f.observe(self.quote(),clock=self.clock,auto_paper=True)["status"],"entry_cancelled")
        self.assertIsNone(f.snapshot(clock=self.clock)["position"])
    def test_gate_and_price_drift_veto(self):
        with self.assertRaises(ValueError):f.queue_auto(self.candidate(),gate=lambda now:False,clock=self.clock)
        self.queue();self.now+=timedelta(seconds=1)
        self.assertEqual(f.observe(self.quote("101"),clock=self.clock,auto_paper=True)["status"],"entry_rejected")
        self.assertIsNone(f.snapshot(clock=self.clock)["position"])
    def test_orchestrator_disabled_before_network(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_AUTO_PAPER_ENABLED":"0"}),patch.object(auto.binance,"run",side_effect=AssertionError("network")):
            with self.assertRaises(ValueError):auto.run(SYM,clock=self.clock)

    def test_pending_fill_rechecks_strategy_gate(self):
        self.queue()
        pred={"feature_at":AT.isoformat(),"lightgbm_return":.01,"river_return":.01}
        with patch.dict(os.environ,{k:"1" for k in auto.bridge.FLAGS}),patch.object(auto.forward,"permitted",return_value=True),patch.object(auto,"evidence",return_value=({"scored":100},pred)),patch.object(auto.memory,"snapshot",return_value={}),patch.object(auto.bridge,"memory_ready",return_value=True),patch.object(auto.strategy_gate,"allowed",return_value=False) as gate,patch.object(auto.binance,"run",return_value={}) as provider:
            auto.observe_pending(SYM,clock=self.clock)
            self.assertFalse(provider.call_args.kwargs["auto_paper"])
            gate.return_value=True
            auto.observe_pending(SYM,clock=self.clock)
            self.assertTrue(provider.call_args.kwargs["auto_paper"])
            gate.side_effect=ValueError("unavailable")
            auto.observe_pending(SYM,clock=self.clock)
            self.assertFalse(provider.call_args.kwargs["auto_paper"])
