import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from tools.solana_pwa_health import status,backup_status,unavailable
from tools.solana_research_backup import FILES
from tools.solana_paper_replay import FALSE_FLAGS
from cyberbot.solana_research_api import research_health

NOW=datetime(2026,11,27,tzinfo=timezone.utc)
def raw():
    return {"status":"preflight_ok","research_only":True,"cpu_sample_pct":10.5,
            "total_ram_bytes":8192,"available_ram_bytes":4096,"disk_free_bytes":8192,"disk_total_bytes":16384,
            "publication_state":"ready","publication_stale":False,"stop_marker_present":False,
            "lock_marker_present":True,"blockers":[],"warnings":[],"private_path":"secret",**FALSE_FLAGS}
def make_set(root,stamp):
    dest=root/"backups"/"solana-20261127";dest.mkdir(parents=True)
    files={}
    for name in FILES:
        (dest/name).write_bytes(b"fixture")
        files[name]={"bytes":7,"records":1}
    (dest/"manifest.json").write_text(json.dumps({"version":1,"kind":"solana_research_backup",
                        "created_utc":stamp.isoformat(),"files":files}))
    return dest

class PwaHealthTests(unittest.TestCase):
    def test_missing_config_is_unknown(self):
        out=status(None)
        self.assertIsNone(out["cpu_sample_pct"])
        self.assertIsNone(out["stop_marker_present"])
        self.assertFalse(out["process_liveness_verified"])
    def test_allowlisted_host_data_and_lock_not_liveness(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_pwa_health.health",return_value=raw()):
            out=status(d)
        self.assertEqual(out["cpu_sample_pct"],10.5)
        self.assertTrue(out["lock_marker_present"])
        self.assertFalse(out["task_state_verified"])
        self.assertNotIn("secret",str(out))
    def test_manifest_age_and_no_integrity_claim(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make_set(root,NOW)
            out=backup_status(root,NOW)
            self.assertEqual(out["state"],"manifest_present")
            self.assertEqual(out["bytes"],14)
            self.assertFalse(out["integrity_rechecked"])
            self.assertEqual(backup_status(root,NOW+timedelta(hours=27))["state"],"overdue")
    def test_incomplete_backup_reported_invalid_without_losing_health(self):
        with tempfile.TemporaryDirectory() as d,patch("tools.solana_pwa_health.health",return_value=raw()):
            root=Path(d);folder=make_set(root,NOW)
            (folder/next(iter(FILES))).unlink()
            out=status(root)
            self.assertEqual(out["backup"]["state"],"invalid")
            self.assertEqual(out["cpu_sample_pct"],10.5)
    def test_api_no_store_and_bad_config(self):
        with patch.dict("os.environ",{"CYBERBOT_SOLANA_PWA_DATA_ROOT":""}):
            r=research_health()
            self.assertEqual(r.headers["cache-control"],"no-store")
            self.assertEqual(json.loads(r.body)["health_state"],"unavailable")
        with patch("cyberbot.solana_research_api.health_status",side_effect=ValueError("private path")):
            r=research_health()
            self.assertEqual(json.loads(r.body)["health_state"],"error")
            self.assertNotIn(b"private path",r.body)
