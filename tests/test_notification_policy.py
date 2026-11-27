import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from tools.notification_policy import route

class NotificationTests(unittest.TestCase):
    def test_quiet_boundaries(self):
        n = {"category":"market","severity":"warning"}
        for h,m,expected in [(7,59,"deferred"),(8,0,"immediate"),(12,30,"immediate"),(23,59,"immediate"),(0,0,"immediate"),(0,29,"immediate"),(0,30,"deferred")]:
            assert route(n, datetime(2026,11,27,h,m,tzinfo=ZoneInfo("Europe/Istanbul")), push_enabled=True) == expected

    def test_critical_override_and_mute(self):
        n = {"category":"risk","severity":"critical"}
        now = datetime(2026,11,27,1,tzinfo=ZoneInfo("Europe/Istanbul"))
        assert route(n, now, push_enabled=True) == "immediate"
        assert route(n, now, push_enabled=True, muted=["risk"]) == "inbox"
        assert route(n, now) == "inbox"
