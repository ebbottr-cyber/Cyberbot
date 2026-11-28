"""Offline regression tests for the refresh gate; no provider calls."""
import csv
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from tools.fund_etf_refresh import run


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name) / "prices.sqlite3"
        self.csv = Path(self.folder.name) / "fund.csv"
        self.job = dict(market="TEFAS", symbol="ABC", currency="TRY",
                        provider="csv", source="TEFAS", csv=str(self.csv))

    def write(self, values):
        with self.csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["symbol", "date", "close"])
            for age, price in values:
                writer.writerow(["ABC", (date.today()-timedelta(days=age)).isoformat(), price])

    def refresh(self):
        return run(self.db, [self.job])["results"][0]

    def test_idempotent(self):
        self.write([(2, "1"), (1, "1.01")])
        self.assertEqual(self.refresh()["inserted"], 2)
        self.assertEqual(self.refresh()["inserted"], 0)

    def test_bad_data(self):
        for rows in [[(10,"1"), (9,"1.01")], [(2,"1"), (1,"3")],
                     [(2,"1"), (2,"1")], [(2,"1"), (-1,"1")],
                     [(2,"1"), (1,"0")]]:
            with self.subTest(rows=rows):
                self.write(rows)
                self.assertEqual(self.refresh()["status"], "blocked")
        self.assertFalse(self.db.exists())

    def test_revision_preserves_archive(self):
        self.write([(2,"1"), (1,"1.01")])
        self.assertEqual(self.refresh()["status"], "quality_checked")
        self.write([(2,"1.02"), (1,"1.01")])
        self.assertEqual(self.refresh()["reason"], "historical_revision_review_required")
        with closing(sqlite3.connect(self.db)) as db, db:
            self.assertEqual(db.execute("SELECT close FROM fund_prices ORDER BY session").fetchall(),
                             [("1",), ("1.01",)])

    def test_disabled_provider(self):
        self.job.update(market="ETF", currency="USD", provider="yahoo")
        self.assertEqual(self.refresh()["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
