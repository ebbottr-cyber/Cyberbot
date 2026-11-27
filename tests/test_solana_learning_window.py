import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from tools.dexterm_research_archive import archive
from tools.solana_paper_replay import collect,window_filter
from tools.solana_learning_cycle import run
from tools.solana_learning_readiness import coverage
from tools.solana_strategy_lab import compare
from tools.solana_paper_replay import FALSE_FLAGS

BASE=datetime(2026,1,1,tzinfo=timezone.utc)
def stamp(s):return (BASE+timedelta(seconds=s)).isoformat()
def entry(s,i):
    return {"mint":"m","timestamp":stamp(s),"input_raw":100000000,"token_amount_raw":200+i,
            "return_raw":99000000,"source_digest":"entry","source_index":i}
def exit_row(e,s):
    return {"mint":e["mint"],"timestamp":stamp(s),"entry_timestamp":e["timestamp"],
            "entry_source_digest":e["source_digest"],"entry_source_index":e["source_index"],
            "token_amount_raw":e["token_amount_raw"],"return_raw":110000000,
            "source_digest":"exit","source_index":0,"exit_only":True}

class LearningWindowTests(unittest.TestCase):
    def test_import_window_half_open_and_limit(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"a.db";files=[]
            for i in range(3):
                f=Path(d)/str(i)
                f.write_text(json.dumps({"source":"dexterm_historical_shortlist_exact_mint_lookup",
                     "status":"no_eligible_pools","lookups":[],"tag":i,**FALSE_FLAGS}))
                files.append(f)
            archive(db,files)
            con=sqlite3.connect(db)
            for i,(key,) in enumerate(con.execute("SELECT digest FROM research_reports ORDER BY digest").fetchall()):
                con.execute("UPDATE research_reports SET imported_utc=? WHERE digest=?",(stamp(i*180),key))
            con.commit();con.close()
            _,stats=collect(db,2,window=(stamp(0),stamp(360)))
            self.assertEqual(stats["bridge_reports_read"],2)
            self.assertFalse(stats["bridge_history_truncated"])
            self.assertEqual(stats["archive_import_window"]["basis"],"archive_import_utc")
            self.assertTrue(collect(db,1,window=(stamp(0),stamp(360)))[1]["bridge_history_truncated"])
    def test_invalid_windows_rejected(self):
        for w in ((stamp(1),stamp(0)),(stamp(0),stamp(31*86400)),(stamp(0),)):
            with self.assertRaises(ValueError):window_filter(w)
    def test_bound_exit_updates_coverage_and_strategy(self):
        rows=[entry(0,0),entry(180,1),entry(3600,2)]
        q=exit_row(rows[0],180)
        self.assertEqual(coverage(rows,exit_quotes=[q])["exact_quantity_matches"],1)
        a=compare(rows);b=compare(rows,exit_quotes=[q])
        self.assertNotEqual(a["dataset_sha256"],b["dataset_sha256"])
        self.assertGreater(b["policies"][0]["full_history"]["closed_positions"],a["policies"][0]["full_history"]["closed_positions"])
    def test_cross_boundary_exit_does_not_change_earlier_strategy(self):
        rows=[entry(i*180,i) for i in range(10)]
        q=exit_row(rows[0],8*180)
        a=compare(rows);b=compare(rows,exit_quotes=[q])
        self.assertEqual([p["earlier_window"] for p in a["policies"]],[p["earlier_window"] for p in b["policies"]])
    def test_cycle_uses_exit_window_and_blocks_truncation(self):
        with tempfile.TemporaryDirectory() as d:
            rows=[entry(i*180,i) for i in range(100)]
            q=exit_row(rows[1],360)
            w=(stamp(0),stamp(86400))
            with patch("tools.solana_learning_cycle.collect",return_value=(rows,{"bridge_history_truncated":False})),patch("tools.solana_learning_cycle.collect_exits",return_value=([q],{"exit_history_truncated":True,"bound_exit_quotes":1})) as reader:
                out=run(Path(d)/"source.db",Path(d)/"history.db",window=w,allow_experiment=True)
            reader.assert_called_once()
            self.assertEqual(reader.call_args.kwargs["window"],w)
            self.assertEqual(out["dataset"]["example_count"],1)
            self.assertIn("archive_window_truncated",out["experiment"]["blockers"])
            self.assertFalse(out["experiment"]["experimental_fit_performed"])
