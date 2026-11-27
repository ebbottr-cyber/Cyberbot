import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from tools.solana_pwa_publish import publish,read,NAME
from tools.solana_learning_cycle import run as learn
from tools.solana_research_scheduler import run
from cyberbot.solana_research_api import research_status

class PublishTests(unittest.TestCase):
    def test_missing_and_partial_clear_metrics(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(read(d)["publication_state"],"unavailable")
            publish(d,"running")
            self.assertIsNone(read(d)["dataset"])
            publish(d,"partial")
            self.assertEqual(read(d)["publication_state"],"partial")
            self.assertFalse(read(d)["live_trading_enabled"])
    def test_ready_report_and_stale_at_read_time(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with patch("tools.solana_learning_cycle.collect",return_value=([],{"bridge_history_truncated":False})):
                report=learn(p/"r.db",p/"h.db")
            report["private_path"]="secret"
            publish(d,"ready",report)
            out=read(d)
            self.assertNotIn("secret",str(out))
            self.assertEqual(out["dataset"]["examples"],0)
            self.assertEqual(read(d,now=datetime.now(timezone.utc)+timedelta(hours=2))["report_freshness"],"stale")
            publish(d,"error")
            self.assertIsNone(read(d)["dataset"])
    def test_bad_report_does_not_replace_previous(self):
        with tempfile.TemporaryDirectory() as d:
            publish(d,"running")
            before=(Path(d)/NAME).read_bytes()
            with self.assertRaises(ValueError):publish(d,"ready",{"real_orders":True})
            self.assertEqual(before,(Path(d)/NAME).read_bytes())
    def test_scheduler_publishes_failure(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_research_scheduler.permissions"),patch("tools.solana_research_scheduler.collect_cycle",return_value={"status":"research_run_partial"}):
            p=Path(d)
            run(p,p/"r.db",p/"h.db",p,enabled=True,publish_pwa=True)
            self.assertEqual(read(d)["publication_state"],"partial")
    def test_api_disabled_and_invalid_report_fail_closed(self):
        with patch.dict("os.environ",{"CYBERBOT_SOLANA_PWA_REPORT_DIR":""}):
            self.assertIn(b'"publication_state":"unavailable"',research_status().body)
        with tempfile.TemporaryDirectory() as d,patch.dict("os.environ",{"CYBERBOT_SOLANA_PWA_REPORT_DIR":d}):
            (Path(d)/NAME).write_text("not json")
            response=research_status()
            self.assertIn(b'"publication_state":"error"',response.body)
            self.assertEqual(response.headers["cache-control"],"no-store")
