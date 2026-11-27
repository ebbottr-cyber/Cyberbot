"""Synthetic tests for isolated aggregate research memory."""
from datetime import datetime, timezone
import os
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from tools.local_research.market_memory import (MARKETS, scope, record, save,
                                                inventory, path_for, equity_records)


class MarketMemoryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.created=datetime(2020,1,1,tzinfo=timezone.utc).isoformat()
        self.env=patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def row(self,market,symbol,interval="5m",source="synthetic",protocol="test"):
        return record(scope(market,symbol,interval,source,protocol),"a"*64,20,
                      {"naive":1.0},self.created)

    def test_isolated_idempotent(self):
        rows=[self.row("BIST","TEST.IS"),self.row("NASDAQ","TEST"),
              self.row("BIST","TEST.IS",source="other"),
              self.row("SOLANA","11111111111111111111111111111111")]
        save(self.root,rows)
        save(self.root,rows)
        markets=inventory(self.root)["markets"]
        self.assertEqual(len(markets["BIST"]["scopes"]),2)
        self.assertEqual(len(markets["NASDAQ"]["scopes"]),1)
        self.assertEqual(len(markets["SOLANA"]["scopes"]),1)
        self.assertEqual(markets["XETRA"]["status"],"AWAITING_EVIDENCE")
        self.assertEqual(markets["FUTURES"]["status"],"AWAITING_EVIDENCE")
        self.assertTrue(all(s["reports"]==1 for m in MARKETS for s in markets[m]["scopes"]))
        for m in MARKETS:
            with closing(sqlite3.connect(path_for(self.root,m))) as db, db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM reports WHERE market<>?",(m,)).fetchone()[0],0)

    def test_rights_gate(self):
        with patch.dict(os.environ,{"CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED":"0"}):
            with self.assertRaises(RuntimeError):
                save(self.root,[])
        self.assertFalse((self.root/"var").exists())

    def test_invalid_scope(self):
        for args in [("NYSE","X","1d","x","x"),("SOLANA","ticker","1m","x","x"),
                     ("BIST","TEST","1m","x","x"),("SOLANA","1"*33,"1m","x","x")]:
            with self.assertRaises(ValueError):
                scope(*args)

    def test_invalid_score(self):
        with self.assertRaises(ValueError):
            record(scope("BIST","TEST","5m","x","x"),"a"*64,20,
                   {"naive":float("nan")},self.created)

    def test_archive_partition(self):
        b={"measured":5,"mae_pct":{"naive":1.0,"mean":2.0,"ar1":3.0}}
        p={"created_at":self.created,"evidence_status":"EXPLORATORY_UNVERIFIED",
           "real_orders":False,"automatic_model_selection":False,
           "profitability_verified":False,"license_verified":False,
           "5m":{m:b for m in MARKETS[:3]},"1d":{m:b for m in MARKETS[:3]}}
        rows=list(equity_records(p,"b"*64))
        self.assertEqual(len(rows),6)
        save(self.root,rows)
        result=inventory(self.root)["markets"]
        self.assertEqual(len(result["BIST"]["scopes"]),2)
        self.assertEqual(result["SOLANA"]["status"],"AWAITING_EVIDENCE")

    def test_protected_path(self):
        path=path_for(self.root,"BIST")
        with patch.dict(os.environ,{"CYBERBOT_LEARNING_DB":str(path)}):
            with self.assertRaises(ValueError):
                save(self.root,[])


if __name__=="__main__":
    unittest.main()
