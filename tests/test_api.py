import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from cyberbot.api import app, ledger

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old=os.environ.get("CYBERBOT_DB")
        os.environ["CYBERBOT_DB"]=str(Path(self.tmp.name)/"api.sqlite3")
        ledger.cache_clear()
        self.client=TestClient(app,base_url="http://127.0.0.1",client=("127.0.0.1",12345))

    def tearDown(self):
        ledger.cache_clear()
        if self.old is None:
            os.environ.pop("CYBERBOT_DB",None)
        else:
            os.environ["CYBERBOT_DB"]=self.old

    def test_panel_and_status(self):
        self.assertIn("OBSIDIAN",self.client.get("/").text)
        self.assertEqual(self.client.get("/api/status").json()["mode"],"synthetic_paper")

    def test_guard_and_buy(self):
        self.assertEqual(self.client.post("/api/paper/buy",json={"symbol":"DEMO-SOL"}).status_code,403)
        h={"x-cyberbot-paper":"1"}
        self.assertEqual(self.client.post("/api/paper/buy",json={"symbol":"DEMO-SOL"},headers={**h,"origin":"https://example.org"}).status_code,403)
        self.assertEqual(self.client.post("/api/paper/buy",json={"symbol":"DEMO-SOL"},headers=h).status_code,200)
        self.assertEqual(self.client.get("/api/status").json()["open_count"],1)

    def test_no_live_routes(self):
        self.assertEqual(self.client.get("/api/live/orders").status_code,404)
