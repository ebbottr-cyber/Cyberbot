import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
from tools.solana_research_scheduler import run,exclusive
from tools.solana_exact_exit_quotes import run as exits

class SchedulerTests(unittest.TestCase):
    def test_opt_in_and_range_before_network(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_research_scheduler.collect_cycle") as collect:
            p=Path(d)
            with self.assertRaises(ValueError):run(p,p/"r.db",p/"h.db",p)
            with self.assertRaises(ValueError):run(p,p/"r.db",p/"h.db",p,enabled=True,cycles=13)
            collect.assert_not_called()
    def test_exclusive_lock(self):
        with tempfile.TemporaryDirectory() as d:
            lock=Path(d)/"x.lock"
            with exclusive(lock):
                self.assertTrue(lock.exists())
                with self.assertRaises(FileExistsError):
                    with exclusive(lock):pass
            self.assertFalse(lock.exists())
    def test_order_and_default_no_fit(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_research_scheduler.permissions"),patch("tools.solana_research_scheduler.collect_cycle",return_value={"status":"research_run_complete"}) as c,patch("tools.solana_research_scheduler.exit_cycle",return_value={"status":"no_due_entries","quotes":[]}) as e,patch("tools.solana_research_scheduler.learning_cycle",return_value={"status":"learning_cycle_complete","experiment_blocked":True}) as l:
            p=Path(d)
            out=run(p,p/"r.db",p/"h.db",p,enabled=True)
            c.assert_called_once();e.assert_called_once();l.assert_called_once()
            self.assertTrue(e.call_args.kwargs["skip_quoted"])
            self.assertFalse(l.call_args.kwargs["allow_experiment"])
            self.assertEqual(out["completed_cycles"],1)
            self.assertFalse(out["real_orders"])
            self.assertTrue(Path(out["runs"][0]["report"]).is_file())
            self.assertFalse((p/"r.db.research.lock").exists())
    def test_partial_collection_stops(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_research_scheduler.permissions"),patch("tools.solana_research_scheduler.collect_cycle",return_value={"status":"research_run_partial"}),patch("tools.solana_research_scheduler.exit_cycle") as e:
            p=Path(d);out=run(p,p/"r.db",p/"h.db",p,enabled=True,cycles=3)
            self.assertEqual(out["stop_reason"],"collection_partial")
            e.assert_not_called()
    def test_stop_marker_between_cycles(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_research_scheduler.permissions"),patch("tools.solana_research_scheduler.collect_cycle",return_value={"status":"research_run_complete"}) as c,patch("tools.solana_research_scheduler.exit_cycle",return_value={"status":"no_due_entries","quotes":[]}),patch("tools.solana_research_scheduler.learning_cycle",return_value={"status":"learning_cycle_complete","experiment_blocked":True}):
            p=Path(d)
            def sleep(_):(p/"r.db.research.stop").touch()
            out=run(p,p/"r.db",p/"h.db",p,enabled=True,cycles=2,sleep=sleep)
            self.assertEqual(out["status"],"scheduler_stopped")
            self.assertEqual(out["completed_cycles"],1)
            c.assert_called_once()
    def test_skip_quoted_entries(self):
        now=datetime(2026,1,1,1,tzinfo=timezone.utc)
        row={"mint":"m","timestamp":"2026-01-01T00:55:00+00:00","token_amount_raw":200,"source_digest":"a","source_index":0}
        with patch("tools.solana_exact_exit_quotes.permissions"),patch("tools.solana_exact_exit_quotes.collect",return_value=([row],{})),patch("tools.solana_exit_history.collect_exits",return_value=([{"entry_source_digest":"a","entry_source_index":0}],{})):
            out=exits("unused",clock=lambda:now,skip_quoted=True)
        self.assertEqual(out["status"],"no_due_entries")
        self.assertEqual(out["attempted_quotes"],0)
