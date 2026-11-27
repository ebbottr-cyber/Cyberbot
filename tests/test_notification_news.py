import tempfile
import unittest
from pathlib import Path
from tools.notification_center import NotificationStore
from tools.notification_news import ingest_feed

class NewsTest(unittest.TestCase):
    def test_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory) / "news.sqlite")
            feed = b"""<rss><channel>
            <item><title>Market update</title><link>https://example.org/news/1</link></item>
            <item><title>Unsafe</title><link>https://other.org/news/2</link></item>
            </channel></rss>"""
            self.assertEqual(ingest_feed(store, feed, "Example", {"example.org"}),
                             {"seen": 2, "published": 1, "rejected": 1, "duplicates": 0})
            self.assertEqual(ingest_feed(store, feed, "Example", {"example.org"})["duplicates"], 1)
            self.assertEqual(len(store.list(category="news")), 1)
            with self.assertRaises(ValueError):
                ingest_feed(store, b"<!DOCTYPE rss><rss/>", "Example", {"example.org"})
