import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from tools.notification_center import NotificationStore
from tools.notification_news_store import NewsStore
from tools.notification_news_pipeline import process_news
from tools.notification_news_sync import sync_news

class NewsSyncTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.news = NewsStore(root / "news.db")
        self.inbox = NotificationStore(root / "inbox.db")
        self.record = dict(title="Interest rate decision", source="FED",
                           url="https://www.federalreserve.gov/example",
                           published_at="2026-11-27T08:00:00+00:00",
                           source_id="example-1", market="NASDAQ")
        self.provider = Mock(return_value='{"summary_tr":"Faiz kararı."}')

    def ingest(self):
        return process_news(self.news, self.record, provider=self.provider,
                            ai_enabled=True, enabled=True)

    def test_disabled(self):
        self.assertEqual(process_news(self.news, self.record, provider=self.provider,
                                     ai_enabled=True), {"status":"disabled"})
        self.provider.assert_not_called()
        self.assertEqual(sync_news(self.news, self.inbox), {"status":"disabled"})
        self.assertEqual(self.inbox.list(), [])

    def test_duplicate_skips_ai(self):
        first = self.ingest()
        second = self.ingest()
        self.assertEqual(first["status"], "saved")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(second["ai_status"], "skipped_duplicate")
        self.assertEqual(first["event_key"], second["event_key"])
        self.provider.assert_called_once()
        self.assertEqual(len(self.news.list()), 1)

    def test_sync_idempotent(self):
        first = self.ingest()
        self.assertEqual(sync_news(self.news, self.inbox, enabled=True),
                         {"published":1,"duplicates":0})
        self.assertEqual(sync_news(self.news, self.inbox, enabled=True),
                         {"published":0,"duplicates":1})
        row, = self.inbox.list()
        self.assertEqual(row["event_key"], first["event_key"])
        self.assertEqual(row["category"], "news")
        self.assertIn("Faiz kararı.", row["body"])
        self.assertIn(self.record["url"], row["body"])

    def test_retry_after_failure(self):
        self.ingest()
        broken = Mock()
        broken.publish.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            sync_news(self.news, broken, enabled=True)
        self.assertEqual(sync_news(self.news, self.inbox, enabled=True)["published"], 1)

    def test_existing_rss_service_cycle(self):
        from unittest.mock import patch
        from tools.notification_service import run_cycle
        from datetime import datetime, timezone
        row = dict(source_id="fed", id="rss-1", origin="official_rss",
                   label=self.record["title"], url=self.record["url"],
                   event_at=self.record["published_at"], market="NASDAQ")
        push, queue = Mock(), Mock()
        with patch.dict("os.environ", {"CYBERBOT_NOTIFICATION_NEWS_BRIDGE":"1"}), \
             patch("tools.notification_existing_news_bridge.read", return_value={"items":[row]}):
            def cycle():
                return run_cycle(self.inbox, push, queue, news_store=self.news,
                                 enabled=True, now=datetime(2026,11,27,1,tzinfo=timezone.utc))
            first, second = cycle(), cycle()
        self.assertEqual(first["existing_news_bridge"]["saved"], 1)
        self.assertEqual(first["research_news"]["published"], 1)
        self.assertEqual(second["existing_news_bridge"]["duplicate"], 1)
        self.assertEqual(second["research_news"]["published"], 0)
        self.assertEqual(len(self.inbox.list(category="news")), 1)
        queue.drain.assert_not_called()

    def test_durable_retry(self):
        from unittest.mock import patch
        from tools.notification_news_retry import drain_news
        self.ingest()
        broken = Mock()
        broken.publish.side_effect = RuntimeError("temporary")
        with patch("time.time", return_value=1000000000):
            self.assertEqual(drain_news(self.news, broken, enabled=True)["retry"], 1)
            self.assertEqual(drain_news(self.news, self.inbox, enabled=True)["published"], 0)
        with patch("time.time", return_value=1000003601):
            self.assertEqual(drain_news(self.news, self.inbox, enabled=True)["published"], 1)
            self.assertEqual(drain_news(self.news, self.inbox, enabled=True)["published"], 0)
        self.assertEqual(len(self.inbox.list()), 1)
