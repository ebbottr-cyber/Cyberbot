"""Offline optimizer tests; no exchange, ledger, or model promotion."""
import importlib.util,os,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import futures_strategy_optimizer as o,futures_lightgbm as b,futures_ai_memory as m

START=datetime(2026,1,1,tzinfo=timezone.utc)
NOW=START+timedelta(days=10)
def sample(n=1200):
    return [{"at":(START+i*b.STEP).isoformat(),"symbol":"BTCUSDT","source":"binance-usdm-public",
             "mid":100+(i%31)*.07+i*.01,"spread_bps":1,"funding_rate":.0001,
             "mark_index_basis_pct":.01,"open_interest":500+i,"book_imbalance":.2,
             "taker_imbalance":.1,"atr_1m_pct":.2,"atr_5m_pct":.5} for i in range(n)]
class Fixed:
    def fit(self,x,y):self.learned=len(y)
    def predict(self,x):return [.01]*len(x)
class Online:
    def __init__(self):self.learned=0;self.before=[]
    def learn_one(self,x,y):self.learned+=1
    def predict_one(self,x):self.before.append(self.learned);return 0.0

def prior():
    states={k:{**m.initial(),"runs":3,"weak_streak":0,"last_end":START.isoformat()} for k in m.MODELS}
    return {"symbol":"BTCUSDT","version":m.VERSION,"data_mode":"local_observations_unverified","states":states}

class OptimizerTests(unittest.TestCase):
    def test_forecasts_causal_training(self):
        rows=b.validate(sample(),"BTCUSDT",NOW)
        train,test,_=b.split(b.build(rows))
        f,r=Fixed(),Online()
        forecasts=o.forecasts(rows,train,test,batch_factory=lambda:f,online_factory=lambda:r)
        self.assertEqual(r.before[0],f.learned)
        self.assertEqual(r.before,list(range(f.learned,f.learned+len(test))))
        self.assertEqual(forecasts[0][1]["lightgbm"],1)
        self.assertEqual(forecasts[0][1]["agreement"],0)
    def test_costs_next_minute_and_funding_boundary(self):
        rows=b.validate(sample(),"BTCUSDT",NOW)
        i=40
        a=o.proxy(rows,i,1,1);z=o.proxy(rows,i,1,2)
        self.assertLess(z,a)
        rows[i]["mid"]*=2
        self.assertEqual(o.proxy(rows,i,1,1),a)
        self.assertIsNone(o.proxy(rows,i,0,1))
        self.assertIsNone(o.proxy(rows,478,1,1))
        rows[i+1]["spread_bps"]=21
        self.assertIsNone(o.proxy(rows,i,1,1))
    def test_quarantine_recovery_and_selection(self):
        s=o.initial()
        s=o.update(s,[-.1],[-.2]);s=o.update(s,[-.1],[-.2])
        self.assertTrue(s["quarantined"])
        for _ in range(3):s=o.update(s,[.3],[.2])
        self.assertFalse(s["quarantined"])
        states={k:o.initial() for k in o.NAMES}
        for _ in range(3):states["lightgbm"]=o.update(states["lightgbm"],[.02]*4,[.01]*4)
        self.assertEqual(o.choose(states),"lightgbm")
        self.assertEqual(o.choose(states,["lightgbm"]),"cash")
        states["river"]=dict(states["lightgbm"])
        self.assertEqual(o.choose(states),"cash")
    def test_block_selection_precedes_outcomes_and_memory_veto(self):
        # Only the LightGBM rule is profitable in this injected outcome fixture.
        def signals(rows,train,test,**kwargs):
            return [(i,{"lightgbm":1,"river":0,"agreement":0,"momentum":0}) for i,x,y in test]
        def proxy(rows,i,side,multiplier):return (.02 if multiplier==1 else .01) if side else None
        with patch.object(o,"forecasts",side_effect=signals),patch.object(o,"proxy",side_effect=proxy):
            d=o.evaluate(sample(),symbol="BTCUSDT",as_of=NOW,prior_memory=prior(),batch_factory=Fixed,online_factory=Online)
            self.assertEqual([v["selected_before_block"] for v in d["blocks"][:3]],["cash"]*3)
            self.assertTrue(all(v["selected_before_block"]=="lightgbm" for v in d["blocks"][3:]))
            self.assertEqual(d["next_research_candidate"],"lightgbm")
            p=prior();p["states"]["lightgbm"]["status"]="quarantined"
            q=o.evaluate(sample(),symbol="BTCUSDT",as_of=NOW,prior_memory=p,batch_factory=Fixed,online_factory=Online)
            self.assertEqual(q["blocks"],d["blocks"])
            self.assertEqual(q["next_research_candidate"],"cash")
            self.assertIn("agreement",q["memory_excluded"])
            self.assertFalse(q["promotion_enabled"]);self.assertFalse(q["real_orders"])
            self.assertEqual(q["actual_action"],"HOLD")
    def test_bad_inputs_and_permissions(self):
        p=prior();p["states"]["lightgbm"]["last_end"]=(NOW+timedelta(minutes=1)).isoformat()
        with self.assertRaises(b.ResearchError):o.memory_exclusions(p,"BTCUSDT",NOW)
        with self.assertRaises(b.ResearchError):o.evaluate(sample(),symbol="BTCUSDT",as_of=NOW,batch_factory=Fixed)
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_STRATEGY_OPTIMIZER_ENABLED":"0"}),patch.object(o,"evaluate",side_effect=AssertionError("disabled")):
            with self.assertRaises(b.ResearchError):o.run(sample(),symbol="BTCUSDT",as_of=NOW)
    @unittest.skipUnless(all(importlib.util.find_spec(k) is not None for k in ("lightgbm","river")),"optional models not installed")
    def test_real_models_smoke(self):
        d=o.evaluate(sample(),symbol="BTCUSDT",as_of=NOW,prior_memory=prior())
        self.assertTrue(d["runtime_verified"])
        self.assertFalse(d["paper_orders"])
