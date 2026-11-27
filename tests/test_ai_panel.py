"""Read-only AI panel API projection and access guard."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from cyberbot.api import app
from cyberbot import ai_panel


class AIPanelTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)

    def test_empty_store_and_no_raw_fields(self):
        report=ai_panel.ai_dashboard.snapshot(self.root)
        report["private_path"]="PRIVATE_MARKER"
        report["research"]["models"]["chronos"]["secret"]="PRIVATE_MARKER"
        projected=ai_panel.project(report)
        self.assertNotIn("PRIVATE_MARKER",json.dumps(projected))
        self.assertFalse(projected["real_orders"])
        self.assertFalse(projected["paper_readiness_verified"])
        self.assertEqual(projected["sections"]["risk_referee"],"REVIEW_BLOCKED")
        self.assertIsNone(projected["resources"])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_bad_report_and_busy(self):
        report=ai_panel.ai_dashboard.snapshot(self.root)
        report["real_orders"]=True
        with self.assertRaises(ValueError):
            ai_panel.project(report)
        with patch.object(ai_panel.ai_dashboard,"snapshot",side_effect=ValueError("PRIVATE_MARKER")):
            with self.assertRaises(HTTPException) as error:
                ai_panel.read()
            self.assertEqual(error.exception.status_code,503)
            self.assertNotIn("PRIVATE_MARKER",error.exception.detail)
        with ai_panel._lock:
            with self.assertRaises(HTTPException) as error:
                ai_panel.read()
            self.assertEqual(error.exception.status_code,429)

    def test_access_and_no_store(self):
        with patch.dict(os.environ,{"CYBERBOT_TAILSCALE_ENABLED":"0"}),patch.object(ai_panel,"ROOT",self.root):
            client=TestClient(app,base_url="http://localhost",client=("127.0.0.1",12345))
            response=client.get("/api/models/local-research")
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers["cache-control"],"no-store")
            self.assertEqual(response.json()["version"],"ai-panel-1")
            denied=client.get("/api/models/local-research",headers={"host":"untrusted.example"})
            self.assertEqual(denied.status_code,403)
            self.assertEqual(list(self.root.iterdir()),[])
