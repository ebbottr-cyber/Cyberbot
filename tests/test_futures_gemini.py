"""Offline contract tests; no Google API requests."""
import json,os,unittest
from unittest.mock import patch
import httpx
from cyberbot import futures_gemini as g,futures_lightgbm as b,futures_river as r

ENV={"CYBERBOT_FUTURES_GEMINI_ENABLED":"1","CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED":"1",
     "CYBERBOT_GEMINI_MODEL":"gemini-test","CYBERBOT_GEMINI_API_KEY":"fixture-only"}
def fixture(model):
    metric={"mae_pct":.2,"direction_accuracy_pct":60}
    return {"version":b.VERSION if model=="lightgbm" else r.VERSION,
            "status":"offline_research_only" if model=="lightgbm" else "offline_prequential_research",
            "symbol":"BTCUSDT","actual_action":"HOLD","data_mode":"local_observations_unverified",
            "horizon_minutes":5,"paper_orders":False,"real_orders":False,"promotion_enabled":False,
            "profitability_verified":False,"observations":300,"runtime_verified":False,
            "test_examples":80,"scored_predictions":175,"drift_events":[{}],
            "metrics":{model:dict(metric),"zero":dict(metric),"trailing_momentum":dict(metric)},
            "private_marker":"not-for-provider"}
def response(codes):
    return {"candidates":[{"finishReason":"STOP","content":{"parts":[
        {"text":json.dumps({"review_codes":codes})}]}}]}

class GeminiTests(unittest.TestCase):
    def test_numeric_only_one_call_and_no_authority(self):
        seen=[]
        def handler(req):
            seen.append(req)
            self.assertEqual(req.method,"POST")
            self.assertEqual(req.url.host,"generativelanguage.googleapis.com")
            self.assertEqual(req.url.path,"/v1beta/models/gemini-test:generateContent")
            self.assertEqual(req.headers["x-goog-api-key"],"fixture-only")
            self.assertNotIn("fixture-only",str(req.url))
            body=json.loads(req.content)
            self.assertNotIn("not-for-provider",req.content.decode())
            self.assertNotIn("tools",body)
            data=json.loads(body["contents"][0]["parts"][0]["text"])
            self.assertFalse(data["same_test_window_verified"])
            self.assertEqual(data["river"]["drift_event_count"],1)
            self.assertEqual(body["generationConfig"]["maxOutputTokens"],512)
            return httpx.Response(200,json=response(["inspect_drift"]))
        with patch.dict(os.environ,ENV):
            out=g.run(fixture("lightgbm"),fixture("river"),transport=httpx.MockTransport(handler))
        self.assertEqual(len(seen),1)
        self.assertEqual(out["review_codes"],["common_test_window","verify_data_provenance","inspect_drift"])
        self.assertEqual(out["actual_action"],"HOLD")
        self.assertIsNone(out["model_ranking"])
        for k in ("real_orders","paper_orders","promotion_enabled","provider_output_verified"):
            self.assertIs(out[k],False)

    def test_permissions_and_invalid_metrics_fail_before_network(self):
        transport=httpx.MockTransport(lambda req:self.fail("network called"))
        a,z=fixture("lightgbm"),fixture("river")
        for key,value in (("CYBERBOT_FUTURES_GEMINI_ENABLED","0"),
                          ("CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED","0"),
                          ("CYBERBOT_GEMINI_API_KEY",""),("CYBERBOT_GEMINI_MODEL","../../bad")):
            with patch.dict(os.environ,{**ENV,key:value}):
                with self.assertRaises(b.ResearchError):g.run(a,z,transport=transport)
        with patch.dict(os.environ,ENV):
            for bad in ({**z,"symbol":"ETHUSDT"},{**z,"paper_orders":True},
                        {**z,"metrics":{**z["metrics"],"river":{"mae_pct":"NaN","direction_accuracy_pct":50}}}):
                with self.assertRaises(b.ResearchError):g.run(a,bad,transport=transport)

    def test_reject_non_schema_and_truncated_output(self):
        for raw in (response(["BUY"]),response([]),response(["inspect_drift","inspect_drift"]),
                    {"candidates":[]},{"candidates":[{"finishReason":"MAX_TOKENS"}]},
                    {"candidates":[{"finishReason":"STOP","content":{"parts":[{"functionCall":{}}]}}]}):
            with self.assertRaises(b.ResearchError):g.parse(raw)
        self.assertEqual(g.parse(response(["check_baselines"])),["check_baselines"])

    def test_no_retry_or_redirect(self):
        for status in (302,429,500):
            calls=[]
            def handler(req):
                calls.append(req);return httpx.Response(status,headers={"Location":"https://example.com"})
            with patch.dict(os.environ,ENV):
                with self.assertRaises(b.ResearchError):
                    g.run(fixture("lightgbm"),fixture("river"),transport=httpx.MockTransport(handler))
            self.assertEqual(len(calls),1)
