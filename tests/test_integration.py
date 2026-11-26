"""Offline API contracts across all shipped modules, using isolated fixture databases."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from cyberbot.api import app,ledger
from cyberbot.learning_api import journal
from tools.cloud_daily import yahoo

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.archive=root/"archive.sqlite3"
        with closing(sqlite3.connect(self.archive)) as db,db:
            db.execute("CREATE TABLE stock_daily(code,date,open,high,low,close,volume,data_source)")
            for i in range(240):
                price=100+(i%13)+i/10
                session=str(date(2020,1,1)+timedelta(days=i))
                db.execute("INSERT INTO stock_daily VALUES(?,?,?,?,?,?,?,?)",("THYAO.IS",session,price,price+1,price-1,price,100,"synthetic-fixture"))
        self.env=patch.dict(os.environ,{"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_EBBOT_DB":str(self.archive),"CYBERBOT_COVERAGE_REPORT":"","CYBERBOT_SHADOW_FILE":"","CYBERBOT_SOLANA_READ_ENABLED":"0","CYBERBOT_LOCAL_LLM_ENABLED":"0","CYBERBOT_CHRONOS_ENABLED":"0","CYBERBOT_TAILSCALE_ENABLED":"0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        ledger.cache_clear();journal.cache_clear()
        self.addCleanup(ledger.cache_clear);self.addCleanup(journal.cache_clear)
        self.c=TestClient(app,base_url="http://127.0.0.1",client=("127.0.0.1",12345))
        self.addCleanup(self.c.close)
        self.h={"X-Cyberbot-Paper":"1"}
    def get(self,path):
        r=self.c.get(path)
        self.assertEqual(r.status_code,200,r.text[:500])
        self.assertEqual(r.headers["cache-control"],"no-store")
        return r.json()
    def post(self,path,body=None):
        r=self.c.post(path,json=body,headers=self.h)
        self.assertEqual(r.status_code,200,r.text[:500])
        return r.json()
    def test_panel_routes(self):
        home=self.c.get("/").text
        for path in ("/data","/traders","/analysis","/strategies","/learning","/models","/development","/futures"):
            self.assertIn('href="'+path+'"',home)
            r=self.c.get(path)
            self.assertEqual(r.status_code,200)
            self.assertIn("Ana panel",r.text)
        self.assertEqual(len(self.get("/api/development")["markets"]),5)
        self.assertEqual(self.c.get("/api/development?mode=invalid").status_code,422)
        self.assertEqual(self.c.get("/manifest.webmanifest").status_code,200)
        self.assertEqual(self.c.get("/sw.js").status_code,200)
    def test_research_paper_isolation(self):
        baseline=self.get("/api/status")
        before=self.archive.read_bytes()
        q="?market=BIST&symbol=THYAO.IS"
        self.assertEqual(len(self.get("/api/data/history"+q)["bars"]),240)
        self.assertFalse(self.get("/api/data/history"+q)["paper_fill_enabled"])
        self.assertEqual(self.get("/api/analysis/history"+q)["verdict"],"research_only")
        self.assertFalse(self.get("/api/strategies/history"+q)["promotion_enabled"])
        self.assertFalse(self.get("/api/models/history"+q)["real_orders"])
        self.assertEqual(self.get("/api/traders/research")["mode"],"synthetic")
        experiment=self.post("/api/learning/run?mode=historical_unverified&market=BIST&symbol=THYAO.IS")
        self.assertTrue(experiment["new"])
        self.assertFalse(self.post("/api/learning/run?mode=historical_unverified&market=BIST&symbol=THYAO.IS")["new"])
        self.assertEqual(self.get("/api/learning/experiment/"+experiment["experiment"]["id"]),experiment["experiment"])
        self.assertEqual(self.archive.read_bytes(),before)
        self.assertEqual(self.get("/api/status"),baseline)
        self.assertEqual(self.c.post("/api/paper/buy",json={"symbol":"THYAO.IS"},headers=self.h).status_code,409)
        s=self.post("/api/paper/buy",{"symbol":"DEMO-BIST"})
        self.assertEqual(s["open_count"],1)
        s=self.post("/api/paper/advance",{})
        self.assertEqual(s["tick"],1)
        self.assertEqual(s["equity_history"][-1]["equity"],s["equity"])
        self.assertEqual(self.post("/api/paper/sell/"+str(s["trades"][0]["id"]),{})["open_count"],0)
        self.assertEqual(self.archive.read_bytes(),before)
    def test_network_default_off(self):
        for path in ("/api/data/solana/scan","/api/traders/wallet?address=invalid","/api/models/summary","/api/models/chronos"):
            self.assertEqual(self.c.post(path,headers=self.h).status_code,403,path)
        self.assertFalse(self.get("/api/data/status")["execution_enabled"])
        self.assertFalse(self.get("/api/models/status")["chronos_configured"])
        self.assertEqual(self.c.post("/api/live/orders",headers=self.h).status_code,404)
        self.assertEqual(self.c.post("/api/paper/advance").status_code,403)
        with self.assertRaises(RuntimeError):yahoo([],None,None)
