import json,sqlite3,tempfile,unittest
from pathlib import Path
from tools.dexterm_research_archive import archive

MINT="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
POOL="31p1hptjhFo6ZD8oBqkfutNXQKGGPyi7YcEAfsyKW777"
FLAGS={"security_verified":False,"live_data_verified":False,"pilot_applied":False,"real_orders":False}

class DexTermArchiveTests(unittest.TestCase):
    def test_archive_idempotent_and_pool_observations(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            a=p/"a.json";b=p/"b.json";db=p/"archive.sqlite3"
            a.write_text(json.dumps({"source":"dexterm_screener_query","status":"diagnostic_complete",
                "candidate_count":1,"candidates":[{"mint":MINT}],**FLAGS}),encoding="utf-8-sig")
            pool={"mint":MINT,"pool":POOL}
            b.write_text(json.dumps({"source":"dexterm_historical_shortlist_exact_mint_lookup","status":"diagnostic_complete",
                "lookups":[{"mint":MINT,"status":"reported_pool_match","pool":pool}],
                "scan":{"reports":[{"candidate":pool,"diagnostic":{"status":"diagnostic_complete"}}],**FLAGS},**FLAGS}))
            d=archive(db,[a,b])
            self.assertEqual((d["new_reports"],d["unique_mints"],d["unique_pools"]),(2,1,1))
            self.assertEqual(d["observation_counts"]["snapshot"],1)
            self.assertFalse(d["real_orders"])
            d=archive(db,[a,b])
            self.assertEqual((d["new_reports"],d["duplicate_reports"],d["total_reports"]),(0,2,2))
    def test_invalid_report_does_not_create_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);a=p/"a.json";db=p/"archive.sqlite3"
            a.write_text(json.dumps({"source":"dexterm_screener_query","status":"diagnostic_complete",
                "candidate_count":1,"candidates":[{"mint":"invalid"}],**FLAGS}))
            with self.assertRaises(ValueError):archive(db,[a])
            self.assertFalse(db.exists())
    def test_unrelated_database_is_not_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);a=p/"a.json";db=p/"other.sqlite3"
            c=sqlite3.connect(db);c.execute("CREATE TABLE unrelated(x)");c.close()
            a.write_text(json.dumps({"status":"offline_review_complete","candidate_count":1,
                "candidates":[{"mint":MINT,"review_status":"excluded"}],**FLAGS}))
            with self.assertRaises(ValueError):archive(db,[a])
            c=sqlite3.connect(db)
            try:self.assertEqual(c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),[("unrelated",)])
            finally:c.close()
