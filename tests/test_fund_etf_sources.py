"""Provider contract fixtures; no network or live-price claims."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from tools.fund_etf_tefas import parse_history,fetch
from tools.fund_etf_source_check import compare_sources
from tools.fund_etf_refresh import refresh,SCHEMA


class SourcesTests(unittest.TestCase):
    def test_tefas_parser(self):
        rows=[dict(fonKodu="AAA",tarih="2025-01-02",fiyat="10.01"),
              dict(fonKodu="AAA",tarih="03.01.2025",fiyat=10.02)]
        self.assertEqual(parse_history({"resultList":rows},"AAA")[1],("AAA","2025-01-03","10.02"))
        for bad in (dict(errorMessage="blocked",resultList=rows),
                    dict(resultList=[rows[0],rows[0]]),
                    dict(resultList=[rows[0],dict(rows[1],fonKodu="BBB")])):
            with self.assertRaises(ValueError):
                parse_history(bad,"AAA")
        with self.assertRaises(ValueError):
            fetch("not-created.sqlite3","AAA")

    def test_permission_gate(self):
        with patch("tools.fund_etf_refresh.tefas") as f:
            with self.assertRaises(ValueError):
                refresh("not-created.sqlite3",dict(market="TEFAS",symbol="AAA",currency="TRY",provider="tefas"))
            f.assert_not_called()

    def test_source_agreement_and_disagreement(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"prices.sqlite3"
            with closing(sqlite3.connect(path)) as db,db:
                db.execute(SCHEMA)
                for src in ("Yahoo Finance","Stooq"):
                    db.executemany("INSERT INTO fund_prices VALUES (?,?,?,?,?,?)",
                        [("ETF","AAA",(date.today()-timedelta(days=i)).isoformat(),"USD","100",src) for i in range(1,31)])
            args=dict(market="ETF",symbol="AAA",currency="USD",primary="Yahoo Finance",secondary="Stooq")
            self.assertEqual(compare_sources(path,**args)["status"],"research_agreement")
            with closing(sqlite3.connect(path)) as db,db:
                db.execute("UPDATE fund_prices SET close='102' WHERE source='Stooq'")
            self.assertEqual(compare_sources(path,**args)["status"],"blocked")
            self.assertFalse(compare_sources(path,**args)["source_switched"])


if __name__=="__main__":
    unittest.main()
