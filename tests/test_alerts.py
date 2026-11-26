import unittest
from decimal import Decimal
from unittest.mock import patch
from fastapi.testclient import TestClient
from cyberbot.api import app
from cyberbot.alerts import compose

class AlertTests(unittest.TestCase):
    def test_severity_and_unknown_coverage(self):
        result=compose({"databases":{"paper":"integrity_error","learning":"not_initialized"},"model_runtime_verified":False},
            {"status":"recorded","last_cycle":{"status":"degraded"}},
            {"status":"stale"},
            {"markets":{"BIST":{"status":"unavailable"},"NASDAQ":{"status":"report_only","target":3400,"downloaded":3399}}},
            {"BIST":{"drawdown":Decimal("10.25"),"at":"2026-11-26T12:00:00Z"}})
        items={x["id"]:x for x in result["items"]}
        self.assertEqual(result["items"][0]["severity"],"critical")
        self.assertEqual(items["coverage-BIST"]["severity"],"info")
        self.assertEqual(items["coverage-NASDAQ"]["severity"],"warning")
        self.assertEqual(items["risk-BIST"]["severity"],"warning")
        self.assertEqual(sum(result["counts"].values()),len(items))
        self.assertFalse(result["push_enabled"])
        self.assertFalse(result["real_orders"])

    def test_route_access_and_no_store(self):
        fixture={"items":[],"counts":{"critical":0,"warning":0,"info":0},"push_enabled":False}
        with patch("cyberbot.operations_api.alerts_snapshot",return_value=fixture):
            with TestClient(app,base_url="http://127.0.0.1",client=("127.0.0.1",12345)) as client:
                r=client.get("/api/alerts")
                self.assertEqual(r.status_code,200)
                self.assertEqual(r.headers["cache-control"],"no-store")
                self.assertEqual(r.json(),fixture)
                self.assertIn("UYARI MERKEZİ",client.get("/alerts").text)
            with TestClient(app,base_url="http://127.0.0.1",client=("192.0.2.10",12345)) as client:
                self.assertEqual(client.get("/api/alerts").status_code,403)
                self.assertEqual(client.get("/alerts").status_code,403)
