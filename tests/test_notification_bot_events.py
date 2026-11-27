import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from tools.notification_center import NotificationStore
from tools.notification_bot_events import publish_event, MARKETS

def emit(store, **overrides):
    args = dict(event_id="event-1", kind="signal", market="BIST", summary="Research only", enabled=True)
    args.update(overrides)
    return publish_event(store, **args)

class NotificationTests(unittest.TestCase):
    def test_disabled_and_dedup(self):
        with TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            store = NotificationStore(tmp_path / "events.sqlite")
            assert not emit(store, enabled=False)
            assert emit(store)
            assert not emit(store)
            assert len(store.list()) == 1

    def test_market_separation(self):
        for market in sorted(MARKETS):
            with self.subTest(market=market):
                with TemporaryDirectory() as directory:
                    tmp_path = Path(directory)
                    store = NotificationStore(tmp_path / "events.sqlite")
                    assert emit(store, market=market)
                    assert store.list()[0]["title"].startswith(market + " |")

    def test_same_id_different_markets(self):
        with TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            store = NotificationStore(tmp_path / "events.sqlite")
            assert emit(store, market="BIST")
            assert emit(store, market="NASDAQ")
            assert len(store.list()) == 2

    def test_live_execution_guard(self):
        with TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            store = NotificationStore(tmp_path / "events.sqlite")
            with self.assertRaises(ValueError):
                emit(store, kind="live_trade_confirmed")
            assert emit(store, kind="paper_trade")
            assert emit(store, kind="live_trade_confirmed", execution_verified=True)
            assert len(store.list()) == 2

    def test_critical_events(self):
        for kind,category in [("risk_alert","risk"),("data_integrity_error","data")]:
            with self.subTest(kind=kind, category=category):
                with TemporaryDirectory() as directory:
                    tmp_path = Path(directory)
                    store = NotificationStore(tmp_path / "events.sqlite")
                    assert emit(store, kind=kind)
                    row = store.list()[0]
                    assert row["category"] == category
                    assert row["severity"] == "critical"

    def test_invalid_events(self):
        for bad in [{"market":"UNKNOWN"},{"kind":"unknown"},{"event_id":""},{"summary":""},{"summary":"x"*501}]:
            with self.subTest(bad=bad):
                with TemporaryDirectory() as directory:
                    tmp_path = Path(directory)
                    store = NotificationStore(tmp_path / "events.sqlite")
                    with self.assertRaises(ValueError):
                        emit(store, **bad)
                    assert not store.list()
