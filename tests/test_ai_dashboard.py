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

    def report_v2(self,status="EXIT_OK"):
        report=self.report()
        report["version"]="ai-watchdog-2"
        report["tasks"].append({"name":"Cyberbot-AI-ResearchReview","status":status})
        report["resources"]["cpu_load_pct"]=32.5
        return report

    def test_v2_cpu_and_review_task(self):
        self.write(self.report_v2())
        result=windows_health(self.root,self.now)
        self.assertEqual(result["status"],"SCHEDULER_OK")
        self.assertTrue(result["research_review_monitored"])
        self.assertEqual(result["resources"]["cpu_load_pct"],32.5)
        self.assertEqual(len(result["tasks"]),6)

    def test_v2_optional_not_enabled(self):
        for status in ("NOT_REGISTERED","DISABLED"):
            self.write(self.report_v2(status))
            self.assertEqual(windows_health(self.root,self.now)["status"],"SCHEDULER_OK")

    def test_v2_failure_and_mismatched_summary(self):
        report=self.report_v2("FAILED")
        self.write(report)
        self.assertEqual(windows_health(self.root,self.now)["status"],"DATA_REVIEW_REQUIRED")
        report["status"]="REVIEW_REQUIRED"
        self.write(report)
        self.assertEqual(windows_health(self.root,self.now)["status"],"REVIEW_REQUIRED")

    def test_v2_requires_all_tasks(self):
        report=self.report_v2()
        report["tasks"].pop()
        self.write(report)
        self.assertEqual(windows_health(self.root,self.now)["status"],"DATA_REVIEW_REQUIRED")

    def test_legacy_missing_cpu_is_unknown(self):
        self.write(self.report())
        result=windows_health(self.root,self.now)
        self.assertFalse(result["research_review_monitored"])
        self.assertIsNone(result["resources"]["cpu_load_pct"])

    def test_invalid_cpu_samples(self):
        for value in (-1,101,True,float("nan")):
            report=self.report_v2()
            report["resources"]["cpu_load_pct"]=value
            self.write(report)
            self.assertEqual(windows_health(self.root,self.now)["status"],"DATA_REVIEW_REQUIRED")

    def test_stale_v2_hides_cpu_and_current_monitoring(self):
        self.write(self.report_v2())
        result=windows_health(self.root,self.now+timedelta(minutes=16))
        self.assertFalse(result["research_review_monitored"])
        self.assertIsNone(result["resources"])
