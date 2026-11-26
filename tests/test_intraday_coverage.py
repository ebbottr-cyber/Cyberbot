import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from cyberbot.api import app
from cyberbot.providers.intraday_coverage import coverage_5m

class IntradayCoverageTests(unittest.TestCase):
    def test_missing_not_zero(self):
        d=coverage_5m()
        self.assertFalse(d["live_progress"])
        self.assertFalse(d["execution_enabled"])
        for m in d["markets"].values():
            self.assertIsNone(m["downloaded"])
            self.assertIsNone(m["missing"])

    def test_reports_and_invalid_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"nasdaq.json"
            p.write_text(json.dumps(dict(candidates=3400,attempted=3399,downloaded=3399,bars_5m=500000,missing_or_failed=["AAPL"])))
            q=Path(tmp)/"bist-xetra.json"
            q.write_text(json.dumps({"BIST":dict(target=803,attempted=803,downloaded=802,rows=1000,missing=["THYAO.IS"]),"XETRA":dict(target=1749,attempted=1748,downloaded=1749,rows=2000,missing=[])}))
            d=coverage_5m(p,q)
            self.assertEqual(d["markets"]["NASDAQ"]["downloaded"],3399)
            self.assertEqual(d["markets"]["BIST"]["missing"],["THYAO.IS"])
            self.assertEqual(d["markets"]["XETRA"]["status"],"unavailable")
            self.assertFalse(d["archive_files_verified"])
            p.write_text("not JSON")
            self.assertIsNone(coverage_5m(p,q)["markets"]["NASDAQ"]["downloaded"])

    def test_api_guard(self):
        with patch.dict("os.environ",{"CYBERBOT_NASDAQ_5M_REPORT":"","CYBERBOT_BIST_XETRA_5M_REPORT":""}):
            with TestClient(app,base_url="http://127.0.0.1",client=("127.0.0.1",12345)) as c:
                r=c.get("/api/data/coverage/5m")
                self.assertEqual(r.status_code,200)
                self.assertEqual(r.headers["cache-control"],"no-store")
                self.assertEqual(r.json()["markets"]["BIST"]["target"],803)
            with TestClient(app,base_url="http://127.0.0.1",client=("192.0.2.10",12345)) as c:
                self.assertEqual(c.get("/api/data/coverage/5m").status_code,403)
