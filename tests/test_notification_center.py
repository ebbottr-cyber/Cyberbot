import tempfile
import unittest
from pathlib import Path
from tools.notification_center import NotificationStore

class NotificationStoreTest(unittest.TestCase):
    def test_news_persistence_and_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notifications.sqlite"
            store = NotificationStore(path)
            args = ("news:1", "news", "warning", "Haber", "Özet", "KAP")
            self.assertTrue(store.publish(*args))
            self.assertFalse(store.publish(*args))
            rows = NotificationStore(path).list(category="news", unread=True)
            self.assertEqual(len(rows), 1)
            self.assertTrue(store.mark_read(rows[0]["id"]))
            self.assertFalse(store.mark_read(rows[0]["id"]))
            self.assertEqual(store.list(unread=True), [])
            self.assertEqual(len(store.list()), 1)

    def test_invalid_category(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory) / "notifications.sqlite")
            with self.assertRaises(ValueError):
                store.publish("1", "invalid", "info", "Title", "Body", "Source")
