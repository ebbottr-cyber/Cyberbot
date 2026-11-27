import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from tools.solana_learning_cycle import run
from tools.solana_pwa_status import snapshot

STATS={"bridge_reports_read":0,"bridge_history_truncated":False,"incomplete_diagnostics":0,
       "excluded_diagnostics":0,"duplicate_quotes":0}

class PwaStatusTests(unittest.TestCase):
    def report(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("tools.solana_learning_cycle.collect",return_value=([],STATS)):
                return run(Path(d)/"source.db",Path(d)/"history.db")
    def test_blocked_cycle_not_live_or_successful_training(self):
        r=self.report();out=snapshot(r)
        self.assertEqual(out["dataset"]["examples"],0)
        self.assertEqual(out["status_label_tr"],"Eğitim engellendi")
        self.assertEqual(out["models"],[])
        self.assertIsNone(out["coverage"]["exact_match_pct"])
        self.assertFalse(out["live_trading_enabled"])
        self.assertFalse(out["market_data_freshness_verified"])
    def test_report_age_does_not_claim_live_market(self):
        r=self.report()
        now=datetime.fromisoformat(r["finished_utc"])+timedelta(hours=2)
        self.assertEqual(snapshot(r,now=now)["report_freshness"],"stale")
        r.pop("finished_utc")
        self.assertEqual(snapshot(r)["report_freshness"],"unknown")
    def test_allowlist_and_mismatch(self):
        r=self.report();r["private_path"]="secret"
        self.assertNotIn("secret",str(snapshot(r)))
        r["dataset"]["dataset_sha256"]="bad"
        with self.assertRaises(ValueError):snapshot(r)
    def test_authority_and_future_time_rejected(self):
        r=self.report();r["real_orders"]=True
        with self.assertRaises(ValueError):snapshot(r)
        r=self.report();r["finished_utc"]=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):snapshot(r)
    def test_partial_collection_keeps_metrics_unavailable(self):
        r=self.report();r.update(status="learning_cycle_partial",stage="collection")
        out=snapshot(r)
        self.assertIsNone(out["dataset"])
        self.assertIsNone(out["coverage"])
        self.assertEqual(out["status_label_tr"],"Veri toplama tamamlanmadı")
