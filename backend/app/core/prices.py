import threading
import time

from .. import config


class PriceStore:
    """In-memory price state, refreshed by the background loop.

    - latest:  {item_id: {high, low, high_ts, low_ts}} from /latest
    - windows: {"5m"/"1h": {item_id: {high, low, high_vol, low_vol, ts}}}

    Resolution prefers fresh /latest values, falling back to 5m then 1h
    window averages when latest is stale. Volumes come from /5m (1h fallback).
    """

    def __init__(self, stale_secs: int = config.STALE_SECS):
        self._stale_secs = stale_secs
        self._lock = threading.Lock()
        self.latest: dict[int, dict] = {}
        self.windows: dict[str, dict[int, dict]] = {"5m": {}, "1h": {}}
        self.last_refresh: float | None = None

    def update_latest(self, data: dict):
        payload = data.get("data", {})
        with self._lock:
            for item_id, d in payload.items():
                self.latest[int(item_id)] = {
                    "high": d.get("high"),
                    "low": d.get("low"),
                    "high_ts": d.get("highTime") or 0,
                    "low_ts": d.get("lowTime") or 0,
                }

    def update_window(self, data: dict, source: str):
        payload = data.get("data", {})
        parsed = {}
        for item_id, d in payload.items():
            parsed[int(item_id)] = {
                "high": d.get("avgHighPrice"),
                "low": d.get("avgLowPrice"),
                "high_vol": d.get("highPriceVolume"),
                "low_vol": d.get("lowPriceVolume"),
                "ts": d.get("timestamp") or int(time.time()),
            }
        with self._lock:
            self.windows[source] = parsed

    def mark_refreshed(self):
        with self._lock:
            self.last_refresh = time.time()

    def _fresh(self, ts: int | None) -> bool:
        if ts is None:
            return False
        # Wiki API timestamps are unix seconds, same unit as time.time()
        return (time.time() - ts) <= self._stale_secs

    def resolve(self, item_id: int) -> dict | None:
        """Per-side price resolution for one item.

        Returns None if the item has no usable price at all. Each side is
        (value, stale, source). Volume sides: (vol, source).
        """
        with self._lock:
            latest = self.latest.get(item_id)
            w5 = self.windows["5m"].get(item_id)
            w1 = self.windows["1h"].get(item_id)

        def side(kind: str):
            if latest and latest.get(kind) is not None and self._fresh(latest.get(f"{kind}_ts")):
                return latest[kind], False, "latest"
            for src in ("5m", "1h"):
                w = w5 if src == "5m" else w1
                if w and w.get(kind) is not None:
                    return w[kind], True, src
            return None, False, None

        high = side("high")
        low = side("low")
        if high[0] is None and low[0] is None:
            return None

        def vol(kind: str):
            for src in ("5m", "1h"):
                w = w5 if src == "5m" else w1
                if w and w.get(kind) is not None:
                    return w[kind], src
            return 0, None

        high_vol = vol("high_vol")
        low_vol = vol("low_vol")

        return {
            "high": high,
            "low": low,
            "high_vol": high_vol,
            "low_vol": low_vol,
        }
