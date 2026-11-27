"""Offline Gemini safety tests: no real API key and no external traffic."""
import json
import tempfile
import unittest
from pathlib import Path
from tools.local_research.gemini_advisory import advise, request_body

ENV = {"CYBERBOT_GEMINI_ENABLED":"1",
       "CYBERBOT_GEMINI_FREE_PROJECT_CONFIRMED":"1",
       "CYBERBOT_GEMINI_DATA_POLICY_ACCEPTED":"1",
       "CYBERBOT_GEMINI_MODEL":"gemini-3.1-flash-lite",
       "CYBERBOT_GEMINI_API_KEY":"synthetic-test-key"}

def reply():
    return 200, {"candidates":[{"finishReason":"STOP","content":{"parts":[
        {"text":json.dumps({"risk":"unknown","checks":["check_data"]})}
    ]}}]}


class GeminiAdvisoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 100000
        self.calls = 0

    def send(self, *args):
        self.calls += 1
        return reply()

    def ask(self, env=ENV, send=None):
        return advise(self.root,"BIST","volatility",env=env,
                      send=send or self.send,clock=lambda:self.now)

    def test_disabled_default(self):
        self.assertEqual(self.ask(env={})["status"],"DISABLED")
        self.assertEqual(self.calls,0)
        self.assertFalse((self.root/"var").exists())

    def test_confirmations_required(self):
        for flag in ("CYBERBOT_GEMINI_FREE_PROJECT_CONFIRMED","CYBERBOT_GEMINI_DATA_POLICY_ACCEPTED"):
            env = dict(ENV)
            env.pop(flag)
            self.assertEqual(self.ask(env=env)["status"],"DISABLED")
        self.assertEqual(self.calls,0)

    def test_invalid_model(self):
        self.assertEqual(self.ask(env={**ENV,"CYBERBOT_GEMINI_MODEL":"other"})["status"],"CONFIGURATION_REQUIRED")
        self.assertEqual(self.calls,0)

    def test_quota_and_interval(self):
        self.assertEqual(self.ask()["status"],"OK")
        self.assertEqual(self.ask()["status"],"WAIT_INTERVAL")
        for _ in range(4):
            self.now += 1800
            self.assertEqual(self.ask()["status"],"OK")
        self.now += 1800
        self.assertEqual(self.ask()["status"],"LOCAL_QUOTA_EXHAUSTED")
        self.assertEqual(self.calls,5)
        self.now += 86400
        self.assertEqual(self.ask()["status"],"OK")

    def test_provider_rejection_latched(self):
        self.assertEqual(self.ask(send=lambda *a:(429,None))["status"],"HTTP_429")
        self.now += 90000
        self.assertEqual(self.ask()["status"],"PROVIDER_REVIEW_REQUIRED")
        self.assertEqual(self.calls,0)

    def test_bad_response_rejected(self):
        result = self.ask(send=lambda *a:(200,{"candidates":[]}))
        self.assertEqual(result["status"],"PROVIDER_ERROR")
        self.assertIsNone(result["advisory"])
        self.assertFalse(result["real_orders"])
        self.assertEqual(self.ask()["status"],"WAIT_INTERVAL")

    def test_no_freeform_context(self):
        with self.assertRaises(ValueError):
            request_body("BIST","private portfolio data")
        body = request_body("BIST","volatility")
        self.assertNotIn("tools",body)
        self.assertEqual(body["generationConfig"]["maxOutputTokens"],512)


if __name__ == "__main__":
    unittest.main()
