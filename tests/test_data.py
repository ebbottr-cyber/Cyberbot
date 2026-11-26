import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from cyberbot.providers.equity import history,DataError
from cyberbot.providers.solana_meme import SolanaMemeFeed

class DataTests(unittest.TestCase):
    def test_read_only_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"archive.sqlite3"
            with closing(sqlite3.connect(p)) as c, c:
                c.execute("CREATE TABLE stock_daily(code,date,open,high,low,close,volume,data_source)")
                c.execute("INSERT INTO stock_daily VALUES('THYAO.IS','2020-01-02',10,12,9,11,100,'fixture')")
            before=p.read_bytes()
            d=history(p,"BIST","THYAO.IS")
            self.assertEqual(d["bars"][0]["close"],11)
            self.assertFalse(d["paper_fill_enabled"])
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(history(p,"BIST","ASELS.IS")["status"],"no_data")
            with self.assertRaises(DataError):
                history(p,"NASDAQ","THYAO.IS")
    def test_missing_archive(self):
        with self.assertRaises(DataError):
            history(None,"BIST","THYAO.IS")
    def test_solana_transport_injected(self):
        calls=[]
        def transport(url):
            calls.append(url)
            return []
        self.assertEqual(SolanaMemeFeed(transport).latest_profiles(1),[])
        self.assertEqual(len(calls),1)
