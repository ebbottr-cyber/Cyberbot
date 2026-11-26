import unittest
import tempfile
from pathlib import Path
from tools.deploy_preflight import validate,PATHS

class DeployPreflightTests(unittest.TestCase):
    def env(self,root):
        return {"CYBERBOT_TAILSCALE_ENABLED":"1","CYBERBOT_TAILSCALE_HOST":"obsidian.example.ts.net","CYBERBOT_TAILSCALE_LOGIN":"owner@example.com","CYBERBOT_TAILSCALE_PORT":"8443","CYBERBOT_TAILSCALE_WRITE":"0",**{k:str(root/v) for k,v in PATHS.items()}}
    def test_valid_and_disabled_writes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();env=self.env(root)
            self.assertEqual(validate(env,root),[])
            env["CYBERBOT_TAILSCALE_WRITE"]="1"
            self.assertTrue(validate(env,root))
    def test_placeholder_and_path_escape(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();env=self.env(root)
            env["CYBERBOT_TAILSCALE_HOST"]="replace-me.example.ts.net"
            env["CYBERBOT_DB"]=str(root.parent/"foreign.sqlite3")
            env["CYBERBOT_NASDAQ_5M_REPORT"]=str(root/"outside.json")
            self.assertEqual(len(validate(env,root)),3)
