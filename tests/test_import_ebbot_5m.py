import sqlite3
from pathlib import Path
import unittest
import tempfile
from tools.import_ebbot_5m import run

class ImportTests(unittest.TestCase):
    def test_readonly_import_and_complete_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.check_import(Path(tmp))

    def check_import(self, tmp_path):
        source=tmp_path/"ebbot.sqlite3"
        dest=tmp_path/"cyberbot.sqlite3"
        with sqlite3.connect(source) as db:
            db.execute("CREATE TABLE candles_5m(market TEXT,ticker TEXT,ts_utc TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,fetched_at_utc TEXT,PRIMARY KEY(market,ticker,ts_utc))")
            for i in range(6):
                db.execute("INSERT INTO candles_5m VALUES (?,?,?,?,?,?,?,?,?)",("NASDAQ","AAPL",f"2026-01-05T14:{30+i*5}:00Z",10+i,12+i,9+i,11+i,100,"2026-01-05T16:00:00Z"))
            db.execute("INSERT INTO candles_5m VALUES (?,?,?,?,?,?,?,?,?)",("NASDAQ","AAPL","2026-01-05T15:00:00Z",10,12,9,11,100,"2026-01-05T16:00:00Z"))
            db.execute("INSERT INTO candles_5m VALUES (?,?,?,?,?,?,?,?,?)",("US_UNMATCHED","ABC","2026-01-05T14:30:00Z",10,12,9,11,100,"2026-01-05T16:00:00Z"))
        before=source.read_bytes()
        result=run(source,dest)
        assert source.read_bytes()==before
        assert result["source_rows"]==8 and result["imported_rows"]==7
        assert result["derived"]=={"15":2,"30":1}
        with sqlite3.connect(dest) as db:
            assert db.execute("SELECT open,high,low,close,volume FROM candles_30m").fetchone()==(10,17,9,16,600)
        with self.assertRaises(ValueError):
            run(source,dest)
        with self.assertRaises(ValueError):
            run(source,source)
