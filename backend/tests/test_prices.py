import time

from pricestore import PriceStore


def make_store(latest=None, w5=None, w1=None, stale_secs=900):
    store = PriceStore(stale_secs=stale_secs)
    if latest:
        store.update_latest({"data": latest})
    for src, data in (("5m", w5), ("1h", w1)):
        if data:
            store.update_window({"data": data}, src)
    return store


def test_fresh_uses_seconds_not_millis():
    """Wiki API timestamps are unix seconds; a 1-minute-old ts must count as fresh."""
    store = PriceStore(stale_secs=900)
    now = int(time.time())
    assert store._fresh(now - 60) is True
    assert store._fresh(now - 1000) is False
    assert store._fresh(None) is False


def test_resolve_prefers_fresh_latest():
    now = int(time.time())
    store = make_store(
        latest={"1": {"high": 100, "low": 90, "highTime": now - 30, "lowTime": now - 30}},
        w5={"1": {"avgHighPrice": 111, "avgLowPrice": 101, "highPriceVolume": 5, "lowPriceVolume": 6, "timestamp": now}},
    )
    r = store.resolve(1)
    assert r["high"] == (100, False, "latest")
    assert r["low"] == (90, False, "latest")


def test_resolve_falls_back_to_windows_when_latest_stale():
    now = int(time.time())
    store = make_store(
        latest={"1": {"high": 100, "low": 90, "highTime": now - 9999, "lowTime": now - 9999}},
        w5={"1": {"avgHighPrice": 111, "avgLowPrice": 101, "highPriceVolume": 5, "lowPriceVolume": 6, "timestamp": now}},
    )
    r = store.resolve(1)
    assert r["high"] == (111, True, "5m")
    assert r["low"] == (101, True, "5m")
    assert r["high_vol"] == (5, "5m")


def test_resolve_1h_fallback_and_missing_sides():
    now = int(time.time())
    store = make_store(
        w1={"2": {"avgHighPrice": 222, "avgLowPrice": None, "highPriceVolume": None, "lowPriceVolume": None, "timestamp": now}},
    )
    r = store.resolve(2)
    assert r["high"] == (222, True, "1h")
    assert r["low"][0] is None
    # volumes fall back to 0 when absent everywhere
    assert r["high_vol"] == (0, None)
    assert store.resolve(999) is None


def test_resolve_none_when_no_data_at_all():
    assert PriceStore().resolve(1) is None
