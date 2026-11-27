import tempfile
import unittest
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.testclient import TestClient
from tools.notification_center import NotificationStore
from tools.notification_api import build_router

class NotificationApiTest(unittest.TestCase):
    def test_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory) / "events.sqlite")
            store.publish("test", "news", "info", "Title", "Body", "Source")
            def require_user(authorization: str = Header(default="")):
                if authorization != "Bearer test-only":
                    raise HTTPException(401)
            app = FastAPI()
            app.include_router(build_router(store, require_user))
            with TestClient(app) as client:
                url = "/api/notifications"
                headers = {"Authorization": "Bearer test-only"}
                self.assertEqual(client.get(url).status_code, 401)
                self.assertEqual(client.get(url + "?category=invalid", headers=headers).status_code, 400)
                items = client.get(url + "?unread=true", headers=headers).json()["items"]
                self.assertEqual(len(items), 1)
                read_url = url + "/" + str(items[0]["id"]) + "/read"
                self.assertEqual(client.post(read_url).status_code, 401)
                self.assertTrue(client.post(read_url, headers=headers).json()["changed"])
                self.assertEqual(client.get(url + "?unread=true", headers=headers).json()["items"], [])
