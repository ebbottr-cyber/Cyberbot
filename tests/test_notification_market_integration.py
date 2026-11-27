import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime, timezone
from tools.notification_center import NotificationStore
from tools.notification_bist_news import ingest_disclosure
from tools.notification_crypto_news import ingest_announcement
from tools.notification_economic_events import normalize_event
from tools.notification_calendar import emit_reminders
from tools.notification_news_filter import matches_news

class NotificationTests(unittest.TestCase):
    def test_bist(self):
        for source,url in [("KAP","https://www.kap.org.tr/example"),("TCMB","https://www.tcmb.gov.tr/example")]:
            with self.subTest(source=source, url=url):
                with TemporaryDirectory() as directory:
                    tmp_path = Path(directory)
                    store=NotificationStore(tmp_path/"news.db")
                    args=dict(source=source,disclosure_id="1",title="Test",published_at="2026-11-27T08:00:00+03:00",url=url,topic="disclosure",symbols=["THYAO"])
                    assert not ingest_disclosure(store,**args)
                    assert ingest_disclosure(store,**args,enabled=True)
                    assert not ingest_disclosure(store,**args,enabled=True)
                    with self.assertRaises(ValueError):
                        ingest_disclosure(store,**{**args,"url":"https://example.com"},enabled=True)

    def test_crypto(self):
        for market,url in [("BINANCE_FUTURES","https://www.binance.com/example"),("SOLANA","https://status.solana.com/example")]:
            with self.subTest(market=market, url=url):
                with TemporaryDirectory() as directory:
                    tmp_path = Path(directory)
                    store=NotificationStore(tmp_path/"news.db")
                    args=dict(market=market,announcement_id="1",title="Test",published_at="2026-11-27T08:00:00+03:00",url=url,topic="security")
                    assert not ingest_announcement(store,**args)
                    assert ingest_announcement(store,**args,enabled=True)
                    assert not ingest_announcement(store,**args,enabled=True)
                    assert store.list()[0]["severity"]=="warning"

    def test_calendar_gate(self):
        with TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            store=NotificationStore(tmp_path/"news.db")
            record=dict(source="FED",type="rate_decision",market="GLOBAL",url="https://www.federalreserve.gov/example",id="1",title="Test",scheduled_at="2026-11-27T10:30:00+00:00",importance="high")
            now=datetime(2026,11,27,10,tzinfo=timezone.utc)
            assert emit_reminders(store,[normalize_event(record)],now)["published"]==0
            event=normalize_event(record,operator_verified=True)
            assert emit_reminders(store,[event],now)["published"]==1
            assert emit_reminders(store,[event],now)["duplicates"]==1

    def test_watchlist(self):
        article=dict(market="BIST",priority="high",symbols=["THYAO"],topics=["earnings"])
        assert matches_news(article,markets=["BIST"],symbols=["thyao"],minimum="high")
        assert not matches_news(article,markets=["NASDAQ"])
        assert not matches_news(article,symbols=["ASELS"])
        assert not matches_news(article,topics=["inflation"])
        assert not matches_news({**article,"priority":"low"},minimum="high")
        assert not matches_news({**article,"market":"GLOBAL"},include_global=False)
