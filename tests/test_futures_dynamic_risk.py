"""Offline Futures dynamic risk policy regression tests."""
import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from copy import deepcopy
from cyberbot import futures_dynamic_risk as r,futures_pilot as fut
from cyberbot.providers import futures_consensus as c
from cyberbot.observed_pilot import PilotError
NOW=datetime(2026,1,1,12,2,tzinfo=timezone.utc)

def fixture():
    state=fut.initial("BTCUSDT")
    state.update(day=NOW.date().isoformat(),quote={"source":"binance-usdm-public",
        "source_at":NOW.isoformat(),"received_at":NOW.isoformat(),"bid":"99.95","ask":"100.05",
        "mark":"100","bid_depth_usdt":"10000","ask_depth_usdt":"10000"})
    report={"version":c.VERSION,"status":"research_only","symbol":"BTCUSDT","evaluated_at":NOW.isoformat(),
            "actual_action":"HOLD","paper_orders":False,"pilot_applied":False,"real_orders":False,
            "research_label":"research_up","blockers":[],
            "risk_context":{"atr_pct":{"1m":".4","5m":".6"},"reported_funding_rate":".0001",
            "directional_semivariance":{f:{"upside_semivariance_20":".000001",
                                           "downside_semivariance_20":".000001"} for f in ("1m","5m")}}}
    return state,report

class DynamicRiskTests(unittest.TestCase):
    def test_long_short_caps_and_no_mutation(self):
        for label in ("research_up","research_down"):
            s,d=fixture();d["research_label"]=label
            original=deepcopy(s)
            result=r.evaluate(s,d,NOW,entry_halted=False);p=result["proposal"]
            self.assertEqual(result["status"],"research_proposal")
            self.assertLessEqual(D(p["margin_usdt"]),100)
            self.assertLessEqual(D(p["modeled_stressed_stop_loss_usdt"]),5)
            self.assertLessEqual(D(p["leverage_cap"]),2)
            self.assertLessEqual(D(p["stop_distance_pct"]),5)
            self.assertLessEqual(D(p["target_distance_pct"]),10)
            if label=="research_up":self.assertTrue(D(p["stop_price"])<D(p["entry"])<D(p["target_price"]))
            else:self.assertTrue(D(p["target_price"])<D(p["entry"])<D(p["stop_price"]))
            self.assertEqual(s,original)
            self.assertEqual(result["actual_action"],"HOLD")
            for flag in ("real_orders","paper_orders","pilot_applied"):self.assertIs(result[flag],False)

    def test_volatility_reduces_exposure_and_vetoes_extreme(self):
        s,d=fixture();low=r.evaluate(s,d,NOW,entry_halted=False)["proposal"]
        d["risk_context"]["atr_pct"]["5m"]="2"
        high=r.evaluate(s,d,NOW,entry_halted=False)["proposal"]
        self.assertEqual(D(high["leverage_cap"]),1)
        self.assertLess(D(high["quantity"]),D(low["quantity"]))
        self.assertLess(D(high["risk_budget_usdt"]),D(low["risk_budget_usdt"]))
        d["risk_context"]["atr_pct"]["5m"]="3"
        self.assertEqual(r.evaluate(s,d,NOW,entry_halted=False)["blockers"],["volatility_exceeds_stop_cap"])

    def test_adverse_directional_semivariance(self):
        s,d=fixture();d["risk_context"]["directional_semivariance"]["5m"]["downside_semivariance_20"]=".0004"
        long=r.evaluate(s,d,NOW,entry_halted=False)["proposal"]
        d["research_label"]="research_down"
        short=r.evaluate(s,d,NOW,entry_halted=False)["proposal"]
        self.assertGreater(D(long["stop_distance_pct"]),D(short["stop_distance_pct"]))
        self.assertLess(D(long["risk_budget_usdt"]),D(short["risk_budget_usdt"]))

    def test_remaining_daily_and_drawdown_budget(self):
        s,d=fixture();s["cash"]="970.1"
        p=r.evaluate(s,d,NOW,entry_halted=False)["proposal"]
        self.assertLessEqual(D(p["modeled_stressed_stop_loss_usdt"]),D(".1"))
        s["cash"]="970"
        self.assertEqual(r.evaluate(s,d,NOW,entry_halted=False)["blockers"],["capital_brake"])
        s,d=fixture();s.update(cash="900.1",day_equity="910")
        p=r.evaluate(s,d,NOW,entry_halted=False)["proposal"]
        self.assertLessEqual(D(p["risk_budget_usdt"]),D(".1"))

    def test_fail_closed(self):
        s,d=fixture()
        self.assertEqual(r.evaluate(s,d,NOW,entry_halted=True)["blockers"],["kill_switch"])
        for changes,reason in (({"position":{"side":"LONG"}},"position_or_pending"),
                               ({"day":"2025-12-31"},"daily_baseline_missing")):
            self.assertEqual(r.evaluate({**s,**changes},d,NOW,entry_halted=False)["blockers"],[reason])
        self.assertEqual(r.evaluate(s,{**d,"research_label":"HOLD"},NOW,entry_halted=False)["blockers"],["consensus_not_confirmed"])
        self.assertEqual(r.evaluate(s,{**d,"evaluated_at":(NOW-timedelta(seconds=31)).isoformat()},NOW,entry_halted=False)["blockers"],["stale_consensus"])
        with self.assertRaises(PilotError):r.evaluate(s,{**d,"symbol":"ETHUSDT"},NOW,entry_halted=False)
        with self.assertRaises(PilotError):r.evaluate(s,{**d,"real_orders":True},NOW,entry_halted=False)
        d["risk_context"]["atr_pct"]["5m"]="NaN"
        with self.assertRaises(PilotError):r.evaluate(s,d,NOW,entry_halted=False)
