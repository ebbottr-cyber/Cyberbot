import pytest
from tools.notification_center import NotificationStore
from tools.notification_bot_events import publish_event, MARKETS

def emit(store, **overrides):
    args = dict(event_id="event-1", kind="signal", market="BIST", summary="Research only", enabled=True)
    args.update(overrides)
    return publish_event(store, **args)

def test_disabled_and_dedup(tmp_path):
    store = NotificationStore(tmp_path / "events.sqlite")
    assert not emit(store, enabled=False)
    assert emit(store)
    assert not emit(store)
    assert len(store.list()) == 1

@pytest.mark.parametrize("market", sorted(MARKETS))
def test_market_separation(tmp_path, market):
    store = NotificationStore(tmp_path / "events.sqlite")
    assert emit(store, market=market)
    assert store.list()[0]["title"].startswith(market + " |")

def test_same_id_different_markets(tmp_path):
    store = NotificationStore(tmp_path / "events.sqlite")
    assert emit(store, market="BIST")
    assert emit(store, market="NASDAQ")
    assert len(store.list()) == 2

def test_live_execution_guard(tmp_path):
    store = NotificationStore(tmp_path / "events.sqlite")
    with pytest.raises(ValueError):
        emit(store, kind="live_trade_confirmed")
    assert emit(store, kind="paper_trade")
    assert emit(store, kind="live_trade_confirmed", execution_verified=True)
    assert len(store.list()) == 2

@pytest.mark.parametrize("kind,category", [("risk_alert","risk"),("data_integrity_error","data")])
def test_critical_events(tmp_path, kind, category):
    store = NotificationStore(tmp_path / "events.sqlite")
    assert emit(store, kind=kind)
    row = store.list()[0]
    assert row["category"] == category
    assert row["severity"] == "critical"

@pytest.mark.parametrize("bad", [{"market":"UNKNOWN"},{"kind":"unknown"},{"event_id":""},{"summary":""},{"summary":"x"*501}])
def test_invalid_events(tmp_path, bad):
    store = NotificationStore(tmp_path / "events.sqlite")
    with pytest.raises(ValueError):
        emit(store, **bad)
    assert not store.list()
