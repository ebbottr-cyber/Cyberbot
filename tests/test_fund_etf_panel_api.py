"""Read-only fund ETF endpoint regression tests."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from cyberbot.fund_etf_api import data, page


class FundETFPanelTests(unittest.TestCase):
    def test_page_contains_market_filters(self):
        html=page()
        self.assertIn("/api/fund-etf",html)
        self.assertIn("TEFAS",html)

    def test_missing_snapshot(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{"CYBERBOT_FUND_ETF_SNAPSHOT":str(Path(folder)/"missing.json")}):
            response=data()
        self.assertEqual(response.status_code,503)

    def test_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"snapshot.json"
            obj=dict(schema_version=1,generated_at=datetime.now(timezone.utc).isoformat(),
                     status="research_only",real_orders=False,execution_allowed=False,
                     instruments=[dict(market="ETF",symbol="ABC",context={"news":["hidden"]})],
                     portfolios=[])
            path.write_text(json.dumps(obj),encoding="utf-8")
            with patch.dict(os.environ,{"CYBERBOT_FUND_ETF_SNAPSHOT":str(path)}):
                response=data()
                obj["real_orders"]=True
                path.write_text(json.dumps(obj),encoding="utf-8")
                rejected=data()
            payload=json.loads(response.body)
            self.assertEqual(response.status_code,200)
            self.assertNotIn("context",payload["instruments"][0])
            self.assertFalse(payload["real_orders"])
            self.assertEqual(rejected.status_code,503)


if __name__=="__main__":
    unittest.main()
