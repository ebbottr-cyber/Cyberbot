import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from tools.notification_center import NotificationStore
from tools.notification_calendar import emit_reminders

class CalendarTest(unittest.TestCase):
    def test_reminder(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory) / "calendar.sqlite")
            now = datetime(2026, 11, 27, 10, tzinfo=timezone.utc)
            event = dict(id="1", title="Test", source="FED", market="NASDAQ",
                         scheduled_at="2026-11-27T13:30:00+03:00",
                         importance="high", verified=True)
            self.assertEqual(emit_reminders(store, [event], now)["published"], 1)
            self.assertEqual(emit_reminders(store, [event], now)["duplicates"], 1)
            self.assertEqual(emit_reminders(store, [dict(event, verified=False)], now)["skipped"], 1)
            self.assertEqual(emit_reminders(store, [dict(event, cancelled=True)], now)["skipped"], 1)
            self.assertEqual(emit_reminders(store, [dict(event, scheduled_at="2026-11-27T10:30:00")], now)["invalid"], 1)
