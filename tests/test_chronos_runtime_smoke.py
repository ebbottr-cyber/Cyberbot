"""Offline preflight checks, no native model needed."""
import json
from pathlib import Path
import tempfile
import unittest
from tools.local_research.chronos_runtime_smoke import check_path, write_report


class ChronosPreflightTests(unittest.TestCase):
    def test_requires_existing_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with self.assertRaises(ValueError):
                check_path(p)
            (p/"config.json").write_text("{}",encoding="utf-8")
            with self.assertRaises(ValueError):
                check_path(p)
            (p/"model.safetensors").write_bytes(b"test fixture, not weights")
            self.assertEqual(check_path(p),p.resolve())

    def test_private_report_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=root/"var/ai"
            folder.mkdir(parents=True)
            report={"runtime_verified":True,"synthetic_only":True}
            path=write_report(root,report)
            self.assertEqual(json.loads(path.read_text()),report)
            self.assertEqual(list(folder.iterdir()),[path])
            self.assertNotEqual(write_report(root,report),path)


if __name__=="__main__":
    unittest.main()
