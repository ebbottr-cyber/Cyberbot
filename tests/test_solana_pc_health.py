import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools.solana_pc_health import health,policy,MIB,MIN_FREE_DISK,MIN_AVAILABLE_RAM

class PcHealthTests(unittest.TestCase):
    def test_thresholds_and_transient_cpu(self):
        self.assertEqual(policy(MIN_FREE_DISK,MIN_AVAILABLE_RAM,90),([],["high_cpu_sample"]))
        b,w=policy(MIN_FREE_DISK-1,MIN_AVAILABLE_RAM-1,None)
        self.assertEqual(b,["low_disk_space","low_available_ram"])
        self.assertIn("cpu_measurement_unavailable",w)
    def test_unknown_memory_not_safe(self):
        self.assertIn("ram_measurement_unavailable",policy(MIN_FREE_DISK,None,10)[0])
    def test_health_is_read_only_and_no_liveness_claim(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_pc_health.windows_resources",return_value=(8192*MIB,2048*MIB,15)),patch("tools.solana_pc_health.shutil.disk_usage",return_value=SimpleNamespace(free=4096*MIB,total=8192*MIB)):
            p=Path(d)
            out=health(p)
            self.assertEqual(out["status"],"preflight_ok")
            self.assertEqual(out["publication_state"],"unavailable")
            self.assertFalse(out["process_liveness_verified"])
            self.assertFalse(out["real_orders"])
            self.assertEqual(list(p.iterdir()),[])
    def test_lock_stop_and_corrupt_report(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_pc_health.windows_resources",return_value=(8192*MIB,2048*MIB,95)),patch("tools.solana_pc_health.shutil.disk_usage",return_value=SimpleNamespace(free=4096*MIB,total=8192*MIB)):
            p=Path(d)
            (p/"solana-research.sqlite3.research.lock").touch()
            (p/"solana-research.sqlite3.research.stop").touch()
            (p/"reports").mkdir()
            (p/"reports"/"solana-research-latest.json").write_text("invalid")
            out=health(p)
            self.assertEqual(out["status"],"preflight_blocked")
            self.assertIn("scheduler_lock_present",out["blockers"])
            self.assertIn("operator_review_stop_marker",out["blockers"])
            self.assertIn("invalid_publication",out["warnings"])
            self.assertIn("high_cpu_sample",out["warnings"])
