import os
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from cyberbot.capital import Portfolio,fx_quote,usd_total
from cyberbot.engine import Ledger,PaperError

class CapitalTests(unittest.TestCase):
    def test_accounts_and_fx(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/"paper.sqlite3";quote=root/"fx.json"
            legacy=Ledger(base);before=legacy.snapshot()
            now=datetime.now(timezone.utc)
            quote.write_text(json.dumps({"usdtry":"45","observed_at":now.isoformat(),"source":"fixture"}))
            with patch.dict(os.environ,{"CYBERBOT_FX_FILE":str(quote),"CYBERBOT_EBBOT_DB":""}):
                p=Portfolio(base);s=p.snapshot()
                self.assertEqual(s["equity"],"4000.00")
                accounts={a["market"]:a for a in s["accounts"]}
                self.assertEqual(accounts["BIST"]["equity"],"45000.00")
                self.assertEqual(accounts["NASDAQ"]["equity"],"1000.00")
                self.assertEqual(accounts["XETRA"]["equity"],"1000.00")
                self.assertEqual(accounts["SOLANA"]["equity"],"1000.00")
                p.ledgers["BIST"].buy("DEMO-BIST")
                self.assertEqual(p.ledgers["NASDAQ"].snapshot()["cash"],"1000.00")
                with self.assertRaises(PaperError):p.ledgers["NASDAQ"].buy("DEMO-BIST")
                self.assertEqual(legacy.snapshot(),before)
                quote.write_text(json.dumps({"usdtry":"50","observed_at":now.isoformat(),"source":"fixture"}))
                self.assertEqual(Portfolio(base).snapshot()["initial_equity_at_current_fx"],"3900.00")
                quote.write_text(json.dumps({"usdtry":"45","observed_at":(now-timedelta(minutes=6)).isoformat(),"source":"fixture"}))
                self.assertIsNone(p.snapshot()["equity"])
                self.assertEqual(p.snapshot()["fx"]["status"],"stale")
    def test_bad_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"fx.json";p.write_text('{"usdtry":"NaN"}')
            self.assertEqual(fx_quote(p)["status"],"unavailable")
