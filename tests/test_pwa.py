import unittest
import struct
from fastapi.testclient import TestClient
from cyberbot.api import app

class PwaTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app,base_url="http://127.0.0.1",client=("127.0.0.1",12345))
    def test_manifest(self):
        r=self.client.get("/manifest.webmanifest")
        self.assertEqual(r.status_code,200)
        self.assertIn("application/manifest+json",r.headers["content-type"])
        self.assertEqual(r.json()["display"],"standalone")
        for icon in r.json()["icons"]:
            p=self.client.get(icon["src"])
            self.assertEqual(p.content[:8],b"\x89PNG\r\n\x1a\n")
            size=int(icon["sizes"].split("x")[0])
            self.assertEqual(struct.unpack(">II",p.content[16:24]),(size,size))
        self.assertEqual(self.client.get("/pwa/icon-999.png").status_code,404)
    def test_worker_and_csp(self):
        r=self.client.get("/sw.js")
        self.assertEqual(r.headers["cache-control"],"no-store")
        self.assertIn("req.method!=='GET'",r.text)
        self.assertIn("cache:'no-store'",r.text)
        self.assertNotIn("caches.open",r.text)
        self.assertIn("worker-src 'self'",self.client.get("/").headers["content-security-policy"])
        self.assertIn("manifest.webmanifest",self.client.get("/").text)
    def test_remote_still_denied(self):
        with TestClient(app,base_url="http://127.0.0.1",client=("192.0.2.10",12345)) as remote:
            self.assertEqual(remote.get("/").status_code,403)
            self.assertEqual(remote.get("/sw.js").status_code,403)
