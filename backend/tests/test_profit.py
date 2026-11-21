import math

import pytest

from app import config
from app.core import profit


class FakeStore:
    """resolve() stub mirroring PriceStore.resolve output shape."""

    def __init__(self, prices):
        # prices: item_id -> {"high": n, "low": n, "high_vol": n, "low_vol": n}
        self.prices = prices

    def resolve(self, item_id):
        p = self.prices.get(item_id)
        if not p:
            return None
        return {
            "high": (p.get("high"), False, "latest"),
            "low": (p.get("low"), False, "latest"),
            "high_vol": (p.get("high_vol", 0), "5m"),
            "low_vol": (p.get("low_vol", 0), "5m"),
        }


ITEMS = {
    1: {"id": 1, "name": "Iron ore", "members": False, "buy_limit": 10000},
    2: {"id": 2, "name": "Coal", "members": False, "buy_limit": 10000},
    3: {"id": 3, "name": "Steel bar", "members": False, "buy_limit": 5000},
    4: {"id": 4, "name": "Cannonball", "members": True, "buy_limit": 10000},
}

RECIPE = {
    "id": "cannonball", "skill": "smithing", "level": 35, "members": True,
    "xp": 25.6,
    "product": {"item_id": 4, "qty": 4},
    "materials": [{"item_id": 3, "qty": 1}],
    "fee": 0, "note": None,
}


def test_tax_exempt_below_threshold():
    limit = config.GE_TAX_EXEMPT_BELOW
    assert profit.ge_tax(limit - 1) == 0
    assert profit.ge_tax(limit) == math.floor(limit * config.GE_TAX_RATE)  # 50 gp itself is taxed (1 coin)
    assert profit.ge_tax(limit + 1) == math.floor((limit + 1) * config.GE_TAX_RATE)


def test_tax_two_percent():
    assert profit.ge_tax(1000) == 20
    assert profit.ge_tax(config.GE_TAX_EXEMPT_BELOW + 50) == math.floor((config.GE_TAX_EXEMPT_BELOW + 50) * config.GE_TAX_RATE)  # floor


def test_tax_cap():
    assert profit.ge_tax(10_000_000_000) == config.GE_TAX_CAP


def test_conservative_mode():
    store = FakeStore({3: {"high": 200, "low": 180}, 4: {"high": 250, "low": 220}})
    row = profit.evaluate_recipe(RECIPE, ITEMS, store, mode="conservative")
    # buy bar @ 200, sell 4 balls @ 220 each
    assert row["xp"] == 25.6
    assert row["cost"] == 200
    assert row["gross"] == 880
    assert row["tax"] == profit.ge_tax(220) * 4
    assert row["net"] == 880 - row["tax"] - 200
    assert row["net_pct"] == round(row["net"] / 200 * 100, 1)
    # limits: 10000 steel bars, 10000/4 product -> 2500 crafts
    assert row["max_crafts_4h"] == 2500
    assert row["net_4h"] == row["net"] * 2500


def test_optimistic_mode_swaps_sides():
    store = FakeStore({3: {"high": 200, "low": 180}, 4: {"high": 250, "low": 220}})
    row = profit.evaluate_recipe(RECIPE, ITEMS, store, mode="optimistic")
    assert row["cost"] == 180
    assert row["gross"] == 1000
    assert row["net"] == 1000 - profit.ge_tax(250) * 4 - 180


def test_missing_price_returns_none():
    store = FakeStore({3: {"high": 200, "low": 180}})  # product missing
    assert profit.evaluate_recipe(RECIPE, ITEMS, store) is None
    store2 = FakeStore({4: {"high": 250, "low": 220}})  # material missing
    assert profit.evaluate_recipe(RECIPE, ITEMS, store2) is None


def test_volume_uses_buy_and_sell_sides():
    store = FakeStore({
        3: {"high": 200, "low": 180, "high_vol": 800, "low_vol": 900},
        4: {"high": 250, "low": 220, "high_vol": 1000, "low_vol": 600},
    })
    row = profit.evaluate_recipe(RECIPE, ITEMS, store, mode="conservative")
    # material buy vol 800 / qty 1 = 800; product sell vol 600 -> 600
    assert row["volume"] == 600


def test_volume_divided_by_material_qty():
    recipe = {
        "id": "x", "skill": "smithing", "level": 1, "members": False,
        "product": {"item_id": 4, "qty": 1},
        "materials": [{"item_id": 3, "qty": 4}], "fee": 0, "note": None,
    }
    store = FakeStore({
        3: {"high": 200, "low": 180, "high_vol": 800, "low_vol": 900},
        4: {"high": 250, "low": 220, "high_vol": 1000, "low_vol": 600},
    })
    row = profit.evaluate_recipe(recipe, ITEMS, store, mode="conservative")
    # 800/4 = 200 vs product sell vol 600 -> 200
    assert row["volume"] == 200


def test_fee_added_to_cost():
    recipe = dict(RECIPE)
    recipe["fee"] = 20
    store = FakeStore({3: {"high": 200, "low": 180}, 4: {"high": 250, "low": 220}})
    row = profit.evaluate_recipe(recipe, ITEMS, store, mode="conservative")
    assert row["cost"] == 220


def test_unknown_limit_sets_net_4h_none():
    items = dict(ITEMS)
    items[3] = {"id": 3, "name": "Steel bar", "members": False, "buy_limit": None}
    store = FakeStore({3: {"high": 200, "low": 180}, 4: {"high": 250, "low": 220}})
    row = profit.evaluate_recipe(RECIPE, items, store)
    assert row["max_crafts_4h"] == 2500  # product limit only
    assert row["net_4h"] is None


def test_unknown_item_returns_none():
    store = FakeStore({3: {"high": 200, "low": 180}, 4: {"high": 250, "low": 220}})
    bad = dict(RECIPE)
    bad["materials"] = [{"item_id": 999, "qty": 1}]
    assert profit.evaluate_recipe(bad, ITEMS, store) is None
