from datetime import datetime
from zoneinfo import ZoneInfo
from tools.notification_policy import route

def test_quiet_boundaries():
    n = {"category":"market","severity":"warning"}
    for h,m,expected in [(7,59,"deferred"),(8,0,"immediate"),(12,29,"immediate"),(12,30,"deferred"),(23,59,"deferred")]:
        assert route(n, datetime(2026,11,27,h,m,tzinfo=ZoneInfo("Europe/Istanbul")), push_enabled=True) == expected

def test_critical_override_and_mute():
    n = {"category":"risk","severity":"critical"}
    now = datetime(2026,11,27,23,tzinfo=ZoneInfo("Europe/Istanbul"))
    assert route(n, now, push_enabled=True) == "immediate"
    assert route(n, now, push_enabled=True, muted=["risk"]) == "inbox"
    assert route(n, now) == "inbox"
