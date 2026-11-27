"""Common-window protocol regression tests; no live APIs or order access."""
import importlib.util,json,os,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import httpx
from cyberbot import futures_ai_consensus as c,futures_lightgbm as b

START=datetime(2026,1,1,tzinfo=timezone.utc)
NOW=START+timedelta(days=10)
def sample(n=300):
    return [{"at":(START+i*b.STEP).isoformat(),"symbol":"BTCUSDT","source":"binance-usdm-public",
             "mid":100+(i%31)*.07+i*.01,"spread_bps":1,"funding_rate":.0001,
             "mark_index_basis_pct":.01,"open_interest":500+i,"book_imbalance":.2,
             "taker_imbalance":.1,"atr_1m_pct":.2,"atr_5m_pct":.5} for i in range(n)]
class Fixed:
    def fit(self,x,y):self.learned=len(y)
    def predict(self,x):return [0.0]*len(x)
class Online:
    def __init__(self):self.learned=0;self.before=[]
    def learn_one(self,x,y):self.learned+=1
    def predict_one(self,x):self.before.append(self.learned);return 0.0
class Detector:
    drift_detected=False
    def update(self,error):pass
class Alarm(Detector):
    def update(self,error):self.drift_detected=True
def evaluate(raw=None,detector=Detector):
    return c.evaluate(sample() if raw is None else raw,symbol="BTCUSDT",as_of=NOW,
                      batch_factory=Fixed,online_factory=Online,detector_factory=detector)

class AIConsensusTests(unittest.TestCase):
    def test_same_window_causal_labels_and_nonoverlap(self):
        f,o=Fixed(),Online()
        d=c.evaluate(sample(),symbol="BTCUSDT",as_of=NOW,batch_factory=lambda:f,
                     online_factory=lambda:o,detector_factory=Detector)
        self.assertEqual(f.learned,o.before[0])
        self.assertEqual(o.before,list(range(f.learned,f.learned+d["all_test"]["examples"])))
        self.assertLess(d["training_last_target_at"],d["test_first_feature_at"])
        self.assertEqual(d["nonoverlapping_test"]["examples"],17)
        self.assertEqual(d["all_test"]["examples"],83)
        self.assertEqual(d["all_test"]["both_hold"],83)
        self.assertEqual(d["all_test"]["both_directional"],0)
        self.assertEqual(d["all_test"]["metrics"]["lightgbm"],d["all_test"]["metrics"]["river"])
        self.assertTrue(d["same_test_window"])
        self.assertIn("insufficient_nonoverlapping_examples",d["blockers"])
        self.assertIn("baseline_not_beaten_by_both",d["blockers"])
        self.assertEqual(d["actual_action"],"HOLD")
        self.assertIsNone(d["model_ranking"])
        for k in ("runtime_verified","promotion_enabled","paper_orders","real_orders","profitability_verified"):
            self.assertIs(d[k],False)

    def test_alarm_timestamps_nonoverlap(self):
        d=evaluate(detector=Alarm)
        self.assertEqual(len(d["drift_events"]),17)
        self.assertIn("river_drift_alarm",d["blockers"])
        dates=[datetime.fromisoformat(row["prediction_at"]) for row in d["drift_events"]]
        self.assertTrue(all(y-x==5*b.STEP for x,y in zip(dates,dates[1:])))
        for row in d["drift_events"]:
            self.assertEqual(datetime.fromisoformat(row["detected_at"])-datetime.fromisoformat(row["prediction_at"]),5*b.STEP)

    def test_disagreement_counts_and_bad_data(self):
        d=c.summarize_pairs([.01,-.01,0],[.01,.01,0],[.02,0,0],[0,0,0])
        self.assertEqual(d["both_directional"],1);self.assertEqual(d["both_hold"],1)
        self.assertEqual(d["disagreements"],1)
        raw=sample();del raw[50]
        with self.assertRaises(b.ResearchError):evaluate(raw)
        with self.assertRaises(b.ResearchError):
            c.evaluate(sample(),symbol="BTCUSDT",as_of=NOW,batch_factory=Fixed)

    def test_gemini_only_numeric_review_and_failure(self):
        d=evaluate();calls=[]
        env={"CYBERBOT_FUTURES_GEMINI_ENABLED":"1","CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED":"1",
             "CYBERBOT_GEMINI_MODEL":"gemini-test","CYBERBOT_GEMINI_API_KEY":"fixture-only"}
        def handler(req):
            calls.append(req);body=json.loads(req.content)
            data=json.loads(body["contents"][0]["parts"][0]["text"])
            self.assertTrue(data["same_test_window"])
            self.assertNotIn("mid",data);self.assertNotIn("features",data)
            self.assertEqual(data["nonoverlapping_examples"],17)
            return httpx.Response(200,json={"candidates":[{"finishReason":"STOP","content":{"parts":[
                {"text":json.dumps({"review_codes":["inspect_drift"]})}]}}]})
        with patch.dict(os.environ,env):
            out=c.gemini_review(d,transport=httpx.MockTransport(handler))
            self.assertEqual(out["review_codes"],["verify_data_provenance","inspect_drift"])
            self.assertEqual(len(calls),1)
            failed=c.gemini_review(d,transport=httpx.MockTransport(lambda _:httpx.Response(429)))
            self.assertEqual(failed["status"],"unavailable")
            self.assertEqual(d["actual_action"],"HOLD")
            with patch.dict(os.environ,{"CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED":"0"}):
                with self.assertRaises(b.ResearchError):c.gemini_review(d,transport=httpx.MockTransport(handler))
        self.assertEqual(len(calls),1)

    def test_disabled_before_evaluation(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_AI_CONSENSUS_ENABLED":"0"}),patch.object(c,"evaluate",side_effect=AssertionError("disabled")):
            with self.assertRaises(b.ResearchError):c.run(sample(),symbol="BTCUSDT",as_of=NOW)

    @unittest.skipUnless(all(importlib.util.find_spec(k) is not None for k in ("lightgbm","river")),"optional models not installed")
    def test_real_estimators_smoke(self):
        d=c.evaluate(sample(),symbol="BTCUSDT",as_of=NOW)
        self.assertTrue(d["runtime_verified"])
        self.assertFalse(d["real_orders"])
