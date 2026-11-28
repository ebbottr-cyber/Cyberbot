"""Offline macro adapter and permission tests. No network credentials required."""
import os
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from tools.fund_etf_context_collect import parse,store,run


class ContextCollectionTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/"archive.sqlite3"
        self.day=date(2025,1,4)
        self.start=date(2025,1,1)

    def test_fred_parser_missing_and_pagination(self):
        payload={"count":2,"observations":[{"date":"2025-01-01","value":"4.2"},
                                         {"date":"2025-01-02","value":"."}]}
        self.assertEqual(parse(payload,"fred","RATE",self.start,self.day),{"2025-01-01":"4.2"})
        payload["count"]=3
        with self.assertRaises(ValueError):
            parse(payload,"fred","RATE",self.start,self.day)

    def test_evds_daily(self):
        payload={"items":[{"Tarih":"02-01-2025","TP_DK_USD_A":"35.1"}]}
        self.assertEqual(parse(payload,"evds","TP.DK.USD.A",self.start,self.day),{"2025-01-02":"35.1"})
        payload["items"].append(dict(payload["items"][0]))
        with self.assertRaises(ValueError):
            parse(payload,"evds","TP.DK.USD.A",self.start,self.day)

    def test_vintage_no_backdating_or_duplicates(self):
        vals={"2025-01-01":"4.2"}
        self.assertEqual(store(self.path,"FRED","RATE","percent",vals,self.day),1)
        self.assertEqual(store(self.path,"FRED","RATE","percent",vals,self.day+timedelta(days=1)),0)
        with self.assertRaises(ValueError):
            store(self.path,"FRED","RATE","percent",{"2025-01-01":"4.3"},self.day)
        self.assertEqual(store(self.path,"FRED","RATE","percent",{"2025-01-01":"4.3"},self.day+timedelta(days=1)),1)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT released FROM fund_macro ORDER BY released").fetchall(),
                             [("2025-01-04",),("2025-01-05",)])

    def test_permission_and_key_not_leaked(self):
        with patch("tools.fund_etf_context_collect.request_json") as req:
            self.assertEqual(run(self.path,[{"provider":"fred"}])["status"],"blocked")
            req.assert_not_called()
            with patch.dict(os.environ,{"FRED_API_KEY":"private-example"}):
                req.side_effect=RuntimeError("private-example")
                result=run(self.path,[dict(provider="fred",series="RATE",unit="percent",
                    rights_confirmed=True,free_access_confirmed=True)])
                self.assertEqual(result["status"],"blocked")
                self.assertNotIn("private-example",json.dumps(result))

    def test_kap_export_freshness(self):
        path=self.path.parent/"kap.json"
        now=datetime.now(timezone.utc)-timedelta(minutes=1)
        path.write_text(json.dumps(dict(exported_at=now.isoformat(),items=[
            dict(source="KAP",market="TEFAS",symbol="AAA",title="fixture",
                 url="https://www.kap.org.tr/tr/Bildirim/123",published=now.isoformat())])),encoding="utf-8")
        job=dict(provider="kap_export",file=str(path),rights_confirmed=True,free_access_confirmed=True)
        self.assertEqual(run(self.path,[job])["results"][0]["inserted"],1)
        self.assertEqual(run(self.path,[job])["results"][0]["inserted"],0)
        path.write_text(json.dumps(dict(exported_at=(now-timedelta(days=2)).isoformat(),items=[])),encoding="utf-8")
        self.assertEqual(run(self.path,[job])["status"],"blocked")


if __name__=="__main__":
    unittest.main()
