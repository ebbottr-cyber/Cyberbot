import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import futures_strategy_gate as g,futures_strategy_optimizer as o,futures_lightgbm as b
AT=datetime(2026,1,1,0,tzinfo=timezone.utc)
class StrategyGateTests(unittest.TestCase):
    def test_quarantine_and_three_block_recovery(self):
        s=g.initial()
        for _ in range(3):s=g.advance(s,"good")
        self.assertEqual(s["state"],"paper_research_eligible")
        s=g.advance(s,"weak");self.assertEqual(s["state"],"observing")
        s=g.advance(s,"weak");self.assertEqual(s["state"],"quarantined")
        s=g.advance(s,"insufficient");self.assertEqual(s["state"],"quarantined")
        for _ in range(2):s=g.advance(s,"good");self.assertEqual(s["state"],"quarantined")
        s=g.advance(s,"good");self.assertEqual(s["state"],"paper_research_eligible")
    def test_empty_window_never_qualifies(self):
        d=g.evaluate_block([],{},AT,AT+timedelta(hours=6))
        self.assertEqual(d["coverage_pct"],0)
        self.assertTrue(all(s["quality"]=="insufficient" for s in d["strategies"].values()))
    def test_proxy_retains_expensive_exit(self):
        rows=[{"at":AT+i*b.STEP,"mid":100,"spread_bps":1} for i in range(6)]
        cheap=o.proxy(rows,0,1,2)
        rows[-1]["spread_bps"]=100
        self.assertLess(o.proxy(rows,0,1,2),cheap)
        rows[1]["spread_bps"]=21
        self.assertIsNone(o.proxy(rows,0,1,2))
    def test_nonpositive_proxy_rejects_report(self):
        rows=[{"at":AT+i*b.STEP,"mid":100,"spread_bps":1} for i in range(6)]
        rows[-1]["spread_bps"]=20000
        with self.assertRaises(ValueError):o.proxy(rows,0,1,2)
    def test_gate_never_accepts_unknown_status(self):
        with self.assertRaises(ValueError):g.advance(g.initial(),"unknown")

    def test_good_forward_block_and_missing_slots(self):
        from cyberbot import futures_ai_bridge as bridge
        end=AT+timedelta(hours=g.HOURS)
        prices={AT+i*b.STEP:{"at":AT+i*b.STEP,"mid":100*1.003**i,"spread_bps":1} for i in range(361)}
        records=[]
        for i in range(0,360,5):
            a=AT+i*b.STEP;z=a+5*b.STEP
            d={"target_received_at":(z-timedelta(seconds=5)).isoformat(),"resolved_at":(z+timedelta(seconds=1)).isoformat(),
               "model_versions":{"lightgbm":b.VERSION,"river":bridge.online.VERSION,"forecast":bridge.VERSION},
               "feature_mid":prices[a]["mid"],"actual_return":prices[z]["mid"]/prices[a]["mid"]-1,
               "predictions":{"lightgbm":.01,"river":.01,"trailing_momentum":0}}
            records.append((a.isoformat(),z.isoformat(),(a+timedelta(seconds=1)).isoformat(),"scored",d))
        result=g.evaluate_block(records,prices,AT,end)
        self.assertEqual(result["scored"],71)
        self.assertEqual(result["strategies"]["agreement"]["quality"],"good")
        self.assertEqual(result["strategies"]["momentum"]["quality"],"insufficient")
        self.assertEqual(g.evaluate_block(records[:40],prices,AT,end)["strategies"]["agreement"]["quality"],"insufficient")
