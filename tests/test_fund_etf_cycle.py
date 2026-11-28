"""Offline orchestration regression tests with synthetic prices."""
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from tools import fund_etf_cycle as engine
from tools.fund_etf_import import ingest
from tools.tefas_catalog import import_catalog


class CycleTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.db=self.root/"archive.sqlite3"
        self.config={"sources":{"TEFAS":"fixture","ETF":"fixture"}}
        catalog=self.root/"catalog.csv"
        catalog.write_text("symbol,name,category\n"+"".join(f"F{i:02},Fund {i},equity\n" for i in range(5)),encoding="utf-8")
        import_catalog(self.db,catalog)
        prices=self.root/"prices.csv"
        lines=["symbol,date,close"]
        for i in range(5):
            for j in range(35):
                day=date.today()-timedelta(days=35-j)
                lines.append(f"F{i:02},{day.isoformat()},{100+j*(i+1)*.1+(j%3)*.01}")
            lines.append(f"F{i:02},{date.today().isoformat()},200")
        prices.write_text("\n".join(lines)+"\n",encoding="utf-8")
        ingest(self.db,prices,"TEFAS","fixture","TRY")

    def test_scan_group_and_conservative_cutoff(self):
        result=engine.cycle(self.db,self.config)
        self.assertEqual(result["status"],"partial")  # ETF catalog absent
        self.assertEqual(result["counts"]["ranked"],5)
        self.assertEqual(result["counts"]["buy_review"],0)  # context unavailable
        self.assertEqual({i["peer_rank"] for i in result["instruments"]},set(range(1,6)))
        self.assertTrue(all(i["metrics"]["last_session"]<date.today().isoformat()
                            for i in result["instruments"]))
        self.assertFalse(result["execution_allowed"])
        with closing(sqlite3.connect(self.db)) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM fund_prices WHERE session=?",
                                        (date.today().isoformat(),)).fetchone()[0],5)

    def test_refresh_failure_blocks_scan(self):
        with patch.object(engine,"refresh",return_value={"status":"blocked"}):
            result=engine.cycle(self.db,dict(self.config,refresh_jobs=[{}]))
        self.assertEqual(result["status"],"blocked")
        self.assertEqual(result["instruments"],[])

    def test_atomic_snapshot_preserves_previous(self):
        output=self.root/"snapshot.json"
        engine.publish({"status":"research_only"},output)
        with self.assertRaises(ValueError):
            engine.publish({"bad":float("nan")},output)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")),
                         {"status":"research_only"})

    def test_catalog_bound(self):
        result=engine.cycle(self.db,dict(self.config,max_instruments=1))
        self.assertEqual(result["status"],"blocked")
        self.assertIn("catalog_limit_exceeded",result["errors"])


if __name__=="__main__":
    unittest.main()
