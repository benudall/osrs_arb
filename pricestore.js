'use strict';
/* Price store — JS port of backend/pricestore.py (the Python file is the
 * reference). Keep both in lockstep; verified via parity fixtures.
 *
 * - latest:  {item_id: {high, low, high_ts, low_ts}} from /latest
 * - windows: {"5m"/"1h": {item_id: {high, low, high_vol, low_vol, ts}}}
 *
 * Resolution prefers fresh /latest values, falling back to 5m then 1h window
 * averages when latest is stale. Volumes come from /5m (1h fallback).
 * nowFn is injectable so parity fixtures can freeze the clock.
 *
 * UMD-ish: browser -> window.OSRSPriceStore, node -> module.exports.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.OSRSPriceStore = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  class PriceStore {
    constructor(staleSecs = 900, nowFn = null) {
      this._staleSecs = staleSecs;
      this._nowFn = nowFn || (() => Date.now() / 1000);
      this.latest = {};
      this.windows = { '5m': {}, '1h': {} };
      this.lastRefresh = null;
    }

    updateLatest(data) {
      const payload = data.data || {};
      for (const [itemId, d] of Object.entries(payload)) {
        this.latest[parseInt(itemId, 10)] = {
          high: d.high ?? null,
          low: d.low ?? null,
          high_ts: d.highTime || 0,
          low_ts: d.lowTime || 0,
        };
      }
    }

    updateWindow(data, source) {
      const payload = data.data || {};
      const parsed = {};
      for (const [itemId, d] of Object.entries(payload)) {
        parsed[parseInt(itemId, 10)] = {
          high: d.avgHighPrice ?? null,
          low: d.avgLowPrice ?? null,
          high_vol: d.highPriceVolume ?? null,
          low_vol: d.lowPriceVolume ?? null,
          ts: d.timestamp || Math.floor(this._nowFn()),
        };
      }
      this.windows[source] = parsed;
    }

    markRefreshed() {
      this.lastRefresh = this._nowFn();
    }

    _fresh(ts, now = null) {
      if (ts == null) return false;
      if (now === null) now = this._nowFn();
      // Wiki API timestamps are unix seconds, same unit as Date.now()/1000
      return (now - ts) <= this._staleSecs;
    }

    /* Per-side price resolution for one item.
     * Returns null if the item has no usable price at all. Each side is
     * [value, stale, source]. Volume sides: [vol, source]. */
    resolve(itemId, now = null) {
      if (now === null) now = this._nowFn();
      const latest = this.latest[itemId];
      const w5 = this.windows['5m'][itemId];
      const w1 = this.windows['1h'][itemId];

      const side = (kind) => {
        if (latest && latest[kind] != null && this._fresh(latest[kind + '_ts'], now)) {
          return [latest[kind], false, 'latest'];
        }
        for (const src of ['5m', '1h']) {
          const w = src === '5m' ? w5 : w1;
          if (w && w[kind] != null) return [w[kind], true, src];
        }
        return [null, false, null];
      };

      const high = side('high');
      const low = side('low');
      if (high[0] === null && low[0] === null) return null;

      const vol = (kind) => {
        for (const src of ['5m', '1h']) {
          const w = src === '5m' ? w5 : w1;
          if (w && w[kind] != null) return [w[kind], src];
        }
        return [0, null];
      };

      return {
        high,
        low,
        high_vol: vol('high_vol'),
        low_vol: vol('low_vol'),
      };
    }
  }

  return PriceStore;
});
