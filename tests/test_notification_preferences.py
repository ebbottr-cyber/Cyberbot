from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import closing
from tools.notification_center import NotificationStore
from tools.notification_preferences import Preferences, morning_digest

def test_preferences_restart(tmp_path):
    path = tmp_path / "prefs.sqlite"
    p = Preferences(path)
    settings = p.load()
    assert settings["quiet_start"] == "00:30"
    assert settings["quiet_end"] == "08:00"
    settings["muted"] = ["news"]
    p.save(settings)
    assert Preferences(path).load() == settings

def test_digest_once(tmp_path):
    store = NotificationStore(tmp_path / "news.sqlite")
    store.publish("news:1","news","info","Example","Body","Test")
    with closing(store.connect()) as db, db:
        db.execute("UPDATE notifications SET created_at=?", ("2026-11-27T04:00:00+00:00",))
    now = datetime(2026,11,27,8,0,tzinfo=ZoneInfo("Europe/Istanbul"))
    assert morning_digest(store, now)
    assert not morning_digest(store, now)
    assert len(store.list()) == 2
