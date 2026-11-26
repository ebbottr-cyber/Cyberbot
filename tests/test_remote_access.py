import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from cyberbot.api import app

ENV={"CYBERBOT_TAILSCALE_ENABLED":"1","CYBERBOT_TAILSCALE_HOST":"pc.example.ts.net","CYBERBOT_TAILSCALE_LOGIN":"owner@example.com","CYBERBOT_TAILSCALE_WRITE":"0","CYBERBOT_TAILSCALE_PORT":"8443"}
HEAD={"Tailscale-User-Login":"owner@example.com"}
class RemoteTests(unittest.TestCase):
    def client(self,host="pc.example.ts.net:8443",peer="127.0.0.1"):
        return TestClient(app,base_url="https://"+host,client=(peer,12345))
    def test_default_denied(self):
        with patch.dict(os.environ,{"CYBERBOT_TAILSCALE_ENABLED":"0"}):
            self.assertEqual(self.client().get("/",headers=HEAD).status_code,403)
    def test_identity_required_all_assets(self):
        with patch.dict(os.environ,ENV):
            c=self.client()
            for path in ("/","/manifest.webmanifest","/sw.js","/api/models/status"):
                self.assertEqual(c.get(path).status_code,403)
                self.assertEqual(c.get(path,headers=HEAD).status_code,200)
            self.assertEqual(c.get("/",headers={"Tailscale-User-Login":"other@example.com"}).status_code,403)
            self.assertEqual(self.client("localhost").get("/",headers=HEAD).status_code,403)
            self.assertEqual(self.client(peer="100.64.0.9").get("/",headers=HEAD).status_code,403)
    def test_read_only_and_origin(self):
        with patch.dict(os.environ,ENV):
            c=self.client()
            headers={**HEAD,"X-Cyberbot-Paper":"1","Origin":"https://pc.example.ts.net:8443"}
            self.assertEqual(c.post("/api/models/summary",headers=headers).status_code,403)
            with patch.dict(os.environ,{"CYBERBOT_TAILSCALE_WRITE":"1"}):
                self.assertEqual(c.post("/not-a-route",headers=HEAD).status_code,403)
                self.assertEqual(c.post("/not-a-route",headers={**headers,"Origin":"https://evil.example"}).status_code,403)
                self.assertEqual(c.post("/not-a-route",headers=headers).status_code,404)
    def test_missing_config(self):
        with patch.dict(os.environ,{**ENV,"CYBERBOT_TAILSCALE_LOGIN":""}):
            self.assertEqual(self.client().get("/",headers=HEAD).status_code,403)
