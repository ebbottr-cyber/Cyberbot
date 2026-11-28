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

    def test_combined_panel_security(self):
        from tools.notification_panel_integration import mount_notification_panel
        from tools.notification_preferences import Preferences
        from tools.notification_push_server import PushStore
        from tools.notification_push_queue import PushQueue
        from tools.notification_news_store import NewsStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = NotificationStore(root / "inbox.db")
            store.publish("test", "news", "info", "Title", "Body", "Source")
            def user(authorization: str = Header(default="")):
                if authorization != "Bearer test-only":
                    raise HTTPException(401)
            def csrf(x_test_csrf: str = Header(default="")):
                if x_test_csrf != "allowed":
                    raise HTTPException(403)
            app = FastAPI()
            args = dict(store=store, preferences=Preferences(root / "prefs.db"),
                        push_store=PushStore(root / "push.db"), queue=PushQueue(root / "queue.db"),
                        health_path=root / "health.json", news_store=NewsStore(root / "news.db"),
                        require_user=user, require_csrf=csrf)
            self.assertFalse(mount_notification_panel(app, **args))
            self.assertTrue(mount_notification_panel(app, enabled=True, **args))
            with self.assertRaises(RuntimeError):
                mount_notification_panel(app, enabled=True, **args)
            auth = {"Authorization": "Bearer test-only"}
            with TestClient(app) as client:
                for path in ("/api/notifications", "/api/notifications/preferences",
                             "/api/notifications/health", "/api/research-news"):
                    self.assertEqual(client.get(path).status_code, 401)
                    self.assertEqual(client.get(path, headers=auth).status_code, 200)
                item = client.get("/api/notifications", headers=auth).json()["items"][0]
                url = "/api/notifications/" + str(item["id"]) + "/read"
                self.assertEqual(client.post(url, headers=auth).status_code, 403)
                self.assertEqual(len(store.list(unread=True)), 1)
                self.assertEqual(client.post(url, headers={**auth, "X-Test-CSRF":"allowed"}).status_code, 200)
                self.assertEqual(store.list(unread=True), [])

    def test_existing_nested_route_collision(self):
        from fastapi import APIRouter
        from tools.notification_panel_integration import mount_notification_panel
        from tools.notification_preferences import Preferences
        from tools.notification_push_server import PushStore
        from tools.notification_push_queue import PushQueue
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = FastAPI()
            child = APIRouter()
            @child.get("/notifications")
            def existing():
                return {"original": True}
            parent = APIRouter(prefix="/api")
            parent.include_router(child)
            app.include_router(parent)
            args = dict(store=NotificationStore(root / "inbox.db"),
                        preferences=Preferences(root / "prefs.db"),
                        push_store=PushStore(root / "push.db"),
                        queue=PushQueue(root / "queue.db"),
                        health_path=root / "health.json",
                        require_user=lambda: None, require_csrf=lambda: None)
            with self.assertRaisesRegex(RuntimeError, "route collision"):
                mount_notification_panel(app, enabled=True, **args)
            self.assertFalse(getattr(app.state, "notification_panel_mounted", False))
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/notifications").json(), {"original": True})
                self.assertEqual(client.get("/api/notifications/preferences").status_code, 404)
            with self.assertRaises(ValueError):
                mount_notification_panel(app, enabled=True, **{**args, "require_csrf": None})
