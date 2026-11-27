import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from cyberbot.integration_api import APP_ID, MARKETS, dexterm_status, integration_status

class IntegrationStatusTests(unittest.TestCase):
    def test_missing_archive_not_created(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"absent.sqlite3"
            self.assertEqual(dexterm_status(path)["status"], "archive_missing")
            self.assertFalse(path.exists())

    def test_wrong_database_not_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"wrong.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE paper (id INT)")
            before = path.read_bytes()
            self.assertEqual(dexterm_status(path)["status"], "archive_unavailable")
            self.assertEqual(path.read_bytes(), before)

    def test_archive_summary_does_not_assert_live_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"dexterm.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("PRAGMA application_id="+str(APP_ID))
                db.execute("PRAGMA user_version=1")
                db.execute("CREATE TABLE research_reports(digest TEXT PRIMARY KEY, kind TEXT, imported_utc TEXT, payload TEXT)")
                db.execute("INSERT INTO research_reports VALUES (?,?,?,?)",("id","screener","2026-11-27T10:00:00+00:00","private payload"))
            before = path.read_bytes()
            state = dexterm_status(path, now=datetime(2026,11,27,10,30,tzinfo=timezone.utc))
            self.assertEqual(state["reports"],1)
            self.assertEqual(state["archive_freshness"],"recent_import")
            self.assertFalse(state["live_data_verified"])
            self.assertNotIn("private payload",str(state))
            self.assertEqual(path.read_bytes(), before)

    @patch("cyberbot.integration_api.dexterm_status",return_value={"status":"archive_available"})
    @patch("cyberbot.integration_api.readiness_snapshot")
    def test_five_markets_and_no_legacy_solana_status(self, readiness, dexterm):
        readiness.return_value={"status":"blocked","markets":[{"market":"SOLANA","data":{"status":"legacy_quote_diagnostics_removed"}},{"market":"FUTURES","data":{"status":"public_adapter_disabled"}}]}
        state=integration_status()
        self.assertEqual(tuple(m["market"] for m in state["markets"]),MARKETS)
        self.assertEqual(state["markets"][-1]["source"],"DexTerm")
        self.assertEqual(state["markets"][-1]["data_status"],"archive_available")
        self.assertFalse(state["markets"][-1]["live_data_verified"])
        self.assertFalse(state["real_orders"])
        self.assertFalse(state["automatic_entry_enabled"])

    @patch("cyberbot.integration_api.dexterm_status",return_value={"status":"not_configured"})
    @patch("cyberbot.integration_api.readiness_snapshot",side_effect=sqlite3.Error)
    def test_readiness_failure_keeps_market_list(self, readiness, dexterm):
        state=integration_status()
        self.assertEqual(len(state["markets"]),5)
        self.assertEqual(state["readiness_status"],"unavailable")
        self.assertTrue(all(not m["live_data_verified"] for m in state["markets"]))

    def test_ai_inventory_is_optional_and_no_authority(self):
        import sys
        from types import ModuleType
        from cyberbot.integration_api import ai_status
        fake=ModuleType("tools.local_research.ai_status")
        fake.run=lambda root: {"version":"ai-status-1","real_orders":False,"automatic_promotion":False,
            "profitability_verified":False,"models":{n:{"status":"RESEARCH_MEASURED","observations_scored":30,"private_path":"SECRET"} for n in ("chronos","river","lightgbm","gemini")}}
        with patch.dict(sys.modules,{"tools.local_research.ai_status":fake}),patch.dict("os.environ",{"CYBERBOT_AI_PANEL_ENABLED":"1"}):
            data=ai_status()
            self.assertEqual(data["status"],"research_inventory_available")
            self.assertEqual(len(data["models"]),4)
            self.assertNotIn("SECRET",str(data))
            self.assertFalse(data["paper_readiness_verified"])
            fake.run=lambda root: {"version":"ai-status-1","real_orders":True}
            self.assertEqual(ai_status()["status"],"unavailable")
        with patch.dict(sys.modules,{"tools.local_research.ai_status":fake}),patch.dict("os.environ",{"CYBERBOT_AI_PANEL_ENABLED":"0"}):
            self.assertEqual(ai_status()["status"],"disabled")
