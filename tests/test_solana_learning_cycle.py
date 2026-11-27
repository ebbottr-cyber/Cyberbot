import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.solana_learning_cycle import run
from tools.solana_model_history import history

STATS={"bridge_reports_read":0,"bridge_history_truncated":False,"incomplete_diagnostics":0,
       "excluded_diagnostics":0,"duplicate_quotes":0}

class LearningCycleTests(unittest.TestCase):
    def test_offline_empty_archive_records_blocked_experiment(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.db";target=Path(d)/"history.db"
            with patch("tools.solana_learning_cycle.collect",return_value=([],STATS)) as reader:
                out=run(source,target)
                reader.assert_called_once_with(source,500)
                self.assertEqual(out["status"],"learning_cycle_complete")
                self.assertTrue(out["experiment_blocked"])
                self.assertFalse(out["collection_requested"])
                self.assertFalse(out["real_orders"])
                self.assertFalse(out["gemini_api_called"])
                self.assertEqual(run(source,target)["history_write"]["status"],"duplicate_ignored")
                self.assertEqual(history(target)["total_experiments"],1)
    def test_partial_collection_stops_before_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.db";target=Path(d)/"history.db"
            with patch("tools.solana_learning_cycle.permissions"),patch("tools.dexterm_research_cycle.run",return_value={"status":"research_run_partial"}) as collector,patch("tools.solana_learning_cycle.collect") as reader:
                out=run(source,target,dexterm_root=d,report_dir=d)
                collector.assert_called_once()
                reader.assert_not_called()
                self.assertEqual(out["stop_reason"],"collection_partial")
                self.assertFalse(target.exists())
    def test_separate_paths_and_explicit_collection(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.db";target=Path(d)/"history.db"
            with self.assertRaises(ValueError):run(source,source)
            with self.assertRaises(ValueError):run(source,target,dexterm_root=d)
            with self.assertRaises(ValueError):run(source,target,limit=501)
    def test_truncated_history_blocks_even_opt_in(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("tools.solana_learning_cycle.collect",return_value=([],dict(STATS,bridge_history_truncated=True))):
                out=run(Path(d)/"source.db",Path(d)/"history.db",allow_experiment=True)
                self.assertIn("archive_window_truncated",out["experiment"]["blockers"])
                self.assertFalse(out["experiment"]["experimental_fit_performed"])
    def test_collection_permission_failure_no_archive_read(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("tools.solana_learning_cycle.permissions",side_effect=ValueError("denied")),patch("tools.solana_learning_cycle.collect") as reader:
                with self.assertRaises(ValueError):run(Path(d)/"source.db",Path(d)/"history.db",dexterm_root=d,report_dir=d)
                reader.assert_not_called()
