import tempfile
import unittest
from pathlib import Path
from datetime import date
from tools.cloud_daily import collect,normalize,universe

class CloudTests(unittest.TestCase):
    def test_resume_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"u.csv"
            p.write_text("market,symbol\ntr,THYAO.IS\nus,AAPL\nde,SAP.DE\n",encoding="utf-8")
            start,end=date(2020,1,1),date(2020,1,5)
            calls=[]
            def fake(symbols,start,end):
                calls.extend(symbols)
                return {s:[("2020-01-02",10,12,9,11,100)] for s in symbols}
            out=Path(tmp)/"out"
            d=collect(p,out,start,end,download=fake,spacing=0)
            self.assertEqual(sum(x["rows_in_range"] for x in d["by_market"].values()),3)
            self.assertEqual(len(calls),3)
            collect(p,out,start,end,download=fake,spacing=0)
            self.assertEqual(len(calls),3)
            with self.assertRaises(ValueError):
                collect(p,out,start,date(2020,1,6))
    def test_bad_rows(self):
        start,end=date(2020,1,1),date(2020,1,5)
        self.assertEqual(normalize([("2020-01-02",10,8,9,11,100)],start,end),[])
        r=("2020-01-02",10,12,9,11,100)
        self.assertEqual(normalize([r,r],start,end),[])
