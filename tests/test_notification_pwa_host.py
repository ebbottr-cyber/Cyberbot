import os
import unittest
from unittest.mock import patch
from starlette.requests import Request
from cyberbot.access import authorize
from cyberbot.pwa import worker, panel_version

class NotificationPwaHostTests(unittest.TestCase):
    def test_worker_disabled_and_enabled(self):
        with patch.dict(os.environ, {"CYBERBOT_NOTIFICATION_PANEL_ENABLED": "0"}):
            baseline = worker().body
            revision = panel_version().body
        with patch.dict(os.environ, {"CYBERBOT_NOTIFICATION_PANEL_ENABLED": "1"}):
            enabled = worker()
            self.assertTrue(enabled.body.startswith(baseline))
            self.assertIn(b'showNotification', enabled.body)
            self.assertIn(b'notificationclick', enabled.body)
            self.assertEqual(enabled.headers["Service-Worker-Allowed"], "/")
            self.assertNotEqual(revision, panel_version().body)
        self.assertNotIn(b'showNotification', baseline)

    def test_remote_read_only_cannot_mutate_notifications(self):
        env = {"CYBERBOT_TAILSCALE_ENABLED": "1",
               "CYBERBOT_TAILSCALE_HOST": "bot.example.ts.net",
               "CYBERBOT_TAILSCALE_LOGIN": "operator@example.invalid",
               "CYBERBOT_TAILSCALE_PORT": "443",
               "CYBERBOT_TAILSCALE_WRITE": "0"}
        headers = [(b"host", b"bot.example.ts.net"),
                   (b"tailscale-user-login", b"operator@example.invalid"),
                   (b"origin", b"https://bot.example.ts.net"),
                   (b"x-cyberbot-paper", b"1")]
        def request(method):
            return Request({"type": "http", "method": method,
                            "path": "/api/notifications/preferences",
                            "headers": headers, "client": ("127.0.0.1", 1234)})
        with patch.dict(os.environ, env):
            self.assertIsNone(authorize(request("GET")))
            for method in ("POST", "PUT", "DELETE"):
                self.assertIsNotNone(authorize(request(method)))

if __name__ == "__main__":
    unittest.main()
