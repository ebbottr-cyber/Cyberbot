import os,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot import futures_ai_bridge as g,futures_ai_memory as m,futures_dynamic_risk as risk,futures_lightgbm as b
NOW=datetime(2026,1,1,12,0,10,tzinfo=timezone.utc)
AT=NOW.replace(second=0)
SYM="BTCUSDT"
def pred():
    return {"lightgbm_return":.01,"river_return":.02,"lightgbm_direction":"UP","river_direction":"UP",
            "feature_at":AT.isoformat(),"feature_mid":100,"estimator_injected":False}
def report():
    return {"version":risk.VERSION,"symbol":SYM,"status":"research_proposal","blockers":[],
            "actual_action":"HOLD","paper_orders":False,"real_orders":False,"pilot_applied":False,
            "evaluated_at":NOW.isoformat(),"quote_reference":{"source":"binance-usdm-public","source_at":NOW.isoformat(),"mid":"100"},
            "proposal":{"side":"LONG","quantity":"0.1"}}
def snap():
    metric=lambda x:{"mae_pct":x}
    recent=[]
    for h in (1,5):
        recent.append({"symbol":SYM,"start":(AT-timedelta(hours=h+3)).isoformat(),"end":(AT-timedelta(hours=h)).isoformat(),
                       "examples":36,"drift_count":0,"metrics":{"lightgbm":metric(.1),"river":metric(.1),"zero":metric(.2),"trailing_momentum":metric(.3)}})
    return {"version":m.VERSION,"symbol":SYM,"data_mode":"local_observations_unverified","recent":recent,
            "states":{k:{**m.initial(),"runs":2,"last_end":recent[0]["end"]} for k in m.MODELS}}
class BridgeTests(unittest.TestCase):
    def test_candidate_is_not_order(self):
        d=g.combine(SYM,pred(),report(),NOW,entry_halted=False)
        self.assertEqual(d["research_candidate"],"LONG")
        self.assertEqual(d["status"],"shadow_candidate")
        self.assertEqual(d["actual_action"],"HOLD")
        for k in ("paper_orders","real_orders","automatic_entry_enabled","promotion_enabled"):self.assertIs(d[k],False)
    def test_vetoes(self):
        for p,r,h,why in [
            (pred(),report(),True,"kill_switch"),
            ({**pred(),"river_return":-.01},report(),False,"ai_disagreement_or_hold"),
            ({**pred(),"estimator_injected":True},report(),False,"injected_estimator"),
            ({**pred(),"feature_at":(AT-timedelta(minutes=2)).isoformat()},report(),False,"stale_ai_features"),
            (pred(),{**report(),"real_orders":True},False,"risk_not_confirmed"),
            (pred(),{**report(),"evaluated_at":(NOW-timedelta(seconds=31)).isoformat()},False,"stale_risk_report"),
            (pred(),{**report(),"proposal":{"side":"SHORT"}},False,"technical_direction_disagreement"),
            (pred(),{**report(),"quote_reference":{**report()["quote_reference"],"mid":"101"}},False,"risk_quote_price_mismatch")]:
            with self.subTest(why=why):
                d=g.combine(SYM,p,r,NOW,entry_halted=h)
                self.assertEqual(d["blockers"],[why]);self.assertIsNone(d["research_candidate"])
    def test_memory_requires_two_nonoverlap_good_windows(self):
        self.assertTrue(g.memory_ready(snap(),SYM,AT))
        s=snap();s["states"]["river"]["status"]="quarantined";self.assertFalse(g.memory_ready(s,SYM,AT))
        s=snap();s["recent"][0]["drift_count"]=1;self.assertFalse(g.memory_ready(s,SYM,AT))
        s=snap();s["recent"][1]["end"]=s["recent"][0]["end"];self.assertFalse(g.memory_ready(s,SYM,AT))
        s=snap();s["recent"][0]["end"]=AT.isoformat();self.assertFalse(g.memory_ready(s,SYM,AT))
    def test_forecast_labels_strictly_before_latest(self):
        raw=[{"at":(AT-timedelta(minutes=299-i)).isoformat(),"symbol":SYM,"source":"binance-usdm-public","mid":100+i*.01,
              "spread_bps":1,"funding_rate":0,"mark_index_basis_pct":0,"open_interest":500,"book_imbalance":0,
              "taker_imbalance":0,"atr_1m_pct":.1,"atr_5m_pct":.2} for i in range(300)]
        rows=b.validate(raw,SYM,NOW)
        class Fixed:
            def fit(self,x,y):self.n=len(y)
            def predict(self,x):return [.01]
        class Online:
            n=0
            def learn_one(self,x,y):self.n+=1
            def predict_one(self,x):return .02
        f,o=Fixed(),Online()
        d=g.forecast(rows,batch_factory=lambda:f,online_factory=lambda:o)
        self.assertEqual(o.n,len(b.build(rows))-1)
        self.assertEqual(f.n,len(b.split(b.build(rows))[0]))
        self.assertTrue(d["estimator_injected"]);self.assertEqual(d["feature_at"],AT.isoformat())
    def test_disabled_before_read(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_AI_BRIDGE_ENABLED":"0"}),patch.object(g.training,"recent",side_effect=AssertionError("disabled")):
            with self.assertRaises(ValueError):g.run(SYM)
