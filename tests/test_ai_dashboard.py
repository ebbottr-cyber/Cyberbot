"""Synthetic health history checks; no Windows APIs or market data needed."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from tools.local_research.ai_dashboard import windows_health, TASKS


class WindowsHealthTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.path=self.root/"var/ai-health/watchdog-history.json"
        self.path.parent.mkdir(parents=True)
        self.now=datetime(2026,1,1,12,tzinfo=timezone.utc)

    def report(self):
        return {"checked_at_utc":self.now.isoformat(),"status":"SCHEDULER_OK",
                "real_orders":False,"task_configuration_modified":False,
                "tasks":[{"name":"Cyberbot-AI-"+name,"status":"EXIT_OK",
                          "unexpected":"private path"} for name in sorted(TASKS)],
                "resources":{"scope":"host_sample_not_process_usage",
                             "free_ram_bytes":4,"total_ram_bytes":16,
                             "free_disk_bytes":20,"total_disk_bytes":100}}

    def write(self,report):
        self.path.write_text(json.dumps([report]),encoding="utf-8")

    def test_missing(self):
        self.assertEqual(windows_health(self.root,self.now)["status"],"NOT_AVAILABLE")

    def test_fresh_and_filtered(self):
        self.write(self.report())
        result=windows_health(self.root,self.now)
        self.assertEqual(result["status"],"SCHEDULER_OK")
        self.assertTrue(result["sample_is_current"])
        self.assertEqual(result["resources"]["free_ram_bytes"],4)
        self.assertNotIn("unexpected",result["tasks"][0])

    def test_stale(self):
        self.write(self.report())
        result=windows_health(self.root,self.now+timedelta(minutes=16))
        self.assertEqual(result["status"],"STALE")
        self.assertIsNone(result["resources"])

    def test_invalid_resources(self):
        report=self.report()
        report["resources"]["free_ram_bytes"]=17
        self.write(report)
        self.assertEqual(windows_health(self.root,self.now)["status"],"DATA_REVIEW_REQUIRED")

    def test_unexpected_task(self):
        report=self.report()
        report["tasks"][0]["name"]="unrelated"
        self.write(report)
        self.assertEqual(windows_health(self.root,self.now)["status"],"DATA_REVIEW_REQUIRED")

    def test_future_and_real_orders(self):
        report=self.report()
        report["checked_at_utc"]=(self.now+timedelta(minutes=1)).isoformat()
        self.write(report)
        self.assertEqual(windows_health(self.root,self.now)["status"],"DATA_REVIEW_REQUIRED")
        report=self.report()
        report["real_orders"]=True
        self.write(report)
        self.assertEqual(windows_health(self.root,self.now)["status"],"DATA_REVIEW_REQUIRED")
