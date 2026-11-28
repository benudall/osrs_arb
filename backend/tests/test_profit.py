import math

import pytest

import config
import profit


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


def test_missing_price_yields_partial_row():
    # missing product price: row still returned, sell side null, alch from value
    store = FakeStore({3: {"high": 200, "low": 180}})
    row = profit.evaluate_recipe(RECIPE, ITEMS, store)
    assert row is not None
    assert row["product"]["price"] is None
    assert row["gross"] is None and row["net"] is None
    assert row["cost"] == 200 and not row["cost_incomplete"]
    # missing material price: cost incomplete, other sides intact
    store2 = FakeStore({4: {"high": 250, "low": 220}})
    row2 = profit.evaluate_recipe(RECIPE, ITEMS, store2)
    assert row2["materials"][0]["price"] is None
    assert row2["cost_incomplete"] is True
    assert row2["gross"] == 880  # conservative: 4 x low 220
    assert row2["cost"] is None  # nothing priced at all -> no cost estimate
    # an unbuyable material kills the direct option entirely (and all, since
    # the material is not craftable either)
    assert row2["cost_direct"] is None and row2["direct_incomplete"] is True
    assert row2["cost_all"] is None and row2["all_incomplete"] is True
    # missing item metadata (not just prices) still returns None
    assert profit.evaluate_recipe(RECIPE, {}, store) is None


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


def test_three_craft_costs():
    # direct = buy every material; mix = cheaper of buy vs recursive
    # craft per material; all = buy roots, craft every intermediate (even when
    # buying an intermediate would be cheaper — that is the scenario priced)
    items = {
        10: {"id": 10, "name": "Bucket of milk", "members": False, "buy_limit": 1000},
        11: {"id": 11, "name": "Cheese", "members": False, "buy_limit": 1000},
        12: {"id": 12, "name": "Tomato", "members": False, "buy_limit": 1000},
        13: {"id": 13, "name": "Uncooked pizza", "members": False, "buy_limit": 1000},
        14: {"id": 14, "name": "Plain pizza", "members": False, "buy_limit": 1000},
    }
    recipes = [
        {"id": "cheese", "skill": "cooking", "level": 1, "members": False,
         "product": {"item_id": 11, "qty": 1},
         "materials": [{"item_id": 10, "qty": 1}], "fee": 0, "note": None},
        {"id": "uncooked_pizza", "skill": "cooking", "level": 1, "members": False,
         "product": {"item_id": 13, "qty": 1},
         "materials": [{"item_id": 11, "qty": 1}, {"item_id": 12, "qty": 1}],
         "fee": 0, "note": None},
        {"id": "plain_pizza", "skill": "cooking", "level": 1, "members": False,
         "product": {"item_id": 14, "qty": 1},
         "materials": [{"item_id": 13, "qty": 1}], "fee": 0, "note": None},
    ]
    # crafting cheese (milk 100) is dearer than buying it (62), so mix buys
    # cheese while all must craft it from the root milk
    store = FakeStore({
        10: {"high": 100, "low": 90},  # milk
        11: {"high": 62, "low": 55},    # cheese
        12: {"high": 23, "low": 20},    # tomato
        13: {"high": 90, "low": 80},    # uncooked pizza
        14: {"high": 120, "low": 110},
    })
    rows, _ = profit.evaluate_all(recipes, items, store)
    by_id = {r["recipe_id"]: r for r in rows}
    cheese = by_id["cheese"]
    # the row cost is the craft cost (buy milk 100); buying cheese itself only
    # competes at the parent's material level
    assert (cheese["cost_direct"], cheese["cost"], cheese["cost_all"]) == (100, 100, 100)
    uncooked = by_id["uncooked_pizza"]
    # direct = cheese 62 + tomato 23; mix = same (buying cheese wins);
    # all = milk 100 + tomato 23
    assert (uncooked["cost_direct"], uncooked["cost"], uncooked["cost_all"]) == (85, 85, 123)
    plain = by_id["plain_pizza"]
    # direct = buy uncooked pizza 90; mix = craft it at its mix cost 85;
    # all = uncooked's all cost 123
    assert (plain["cost_direct"], plain["cost"], plain["cost_all"]) == (90, 85, 123)
    assert not plain["direct_incomplete"] and not plain["cost_incomplete"] and not plain["all_incomplete"]


def test_direct_unavailable_when_material_unbuyable():
    # Amulet of defence case: a material with no GE price but with its own
    # (priced) recipe. Mix and all craft it fine; direct cannot buy it -> None
    items = {
        20: {"id": 20, "name": "Gold bar", "members": False, "buy_limit": 1000},
        21: {"id": 21, "name": "Emerald amulet", "members": False, "buy_limit": 1000},
        22: {"id": 22, "name": "Amulet of defence", "members": False, "buy_limit": 1000},
    }
    recipes = [
        {"id": "emerald_amulet", "skill": "crafting", "level": 1, "members": False,
         "product": {"item_id": 21, "qty": 1},
         "materials": [{"item_id": 20, "qty": 1}], "fee": 0, "note": None},
        {"id": "strung_amulet", "skill": "crafting", "level": 1, "members": False,
         "product": {"item_id": 22, "qty": 1},
         "materials": [{"item_id": 21, "qty": 1}], "fee": 0, "note": None},
    ]
    store = FakeStore({20: {"high": 200, "low": 180}})  # 21 unpriced on the GE
    rows, _ = profit.evaluate_all(recipes, items, store)
    by_id = {r["recipe_id"]: r for r in rows}
    amulet = by_id["strung_amulet"]
    assert amulet["cost_direct"] is None and amulet["direct_incomplete"] is True
    # mix and all price the emerald amulet via its own recipe (gold bar 200)
    assert amulet["cost"] == 200 and not amulet["cost_incomplete"]
    assert amulet["cost_all"] == 200 and not amulet["all_incomplete"]
    # the unstrung amulet row itself is fine: its material (gold bar) is buyable
    unstrung = by_id["emerald_amulet"]
    assert (unstrung["cost_direct"], unstrung["cost"], unstrung["cost_all"]) == (200, 200, 200)


def test_craft_all_all_incomplete_without_prices():
    # no prices at all: every cost variant is None, flags set
    store = FakeStore({})
    row = profit.evaluate_recipe(RECIPE, ITEMS, store)
    assert row["cost_direct"] is None and row["direct_incomplete"]
    assert row["cost"] is None and row["cost_incomplete"]
    assert row["cost_all"] is None and row["all_incomplete"]


def test_craft_costs_recursive():
    # milk -> cheese -> uncooked pizza -> plain pizza: a parent chain must price
    # each material at its fully recursive craft cost, not the buy-only one
    # level the old two-pass evaluate_all produced (the pizza bug: Plain pizza
    # showed Uncooked pizza at the buy-everything cost instead of its own
    # craft-decomposed cost).
    items = {
        10: {"id": 10, "name": "Bucket of milk", "members": False, "buy_limit": 1000},
        11: {"id": 11, "name": "Cheese", "members": False, "buy_limit": 1000},
        12: {"id": 12, "name": "Tomato", "members": False, "buy_limit": 1000},
        13: {"id": 13, "name": "Uncooked pizza", "members": False, "buy_limit": 1000},
        14: {"id": 14, "name": "Plain pizza", "members": False, "buy_limit": 1000},
    }
    recipes = [
        {"id": "cheese", "skill": "cooking", "level": 1, "members": False,
         "product": {"item_id": 11, "qty": 1},
         "materials": [{"item_id": 10, "qty": 1}], "fee": 0, "note": None},
        {"id": "uncooked_pizza", "skill": "cooking", "level": 1, "members": False,
         "product": {"item_id": 13, "qty": 1},
         "materials": [{"item_id": 11, "qty": 1}, {"item_id": 12, "qty": 1}],
         "fee": 0, "note": None},
        {"id": "plain_pizza", "skill": "cooking", "level": 1, "members": False,
         "product": {"item_id": 14, "qty": 1},
         "materials": [{"item_id": 13, "qty": 1}], "fee": 0, "note": None},
    ]
    store = FakeStore({
        10: {"high": 13, "low": 10},   # milk
        11: {"high": 62, "low": 55},   # cheese: crafting (13) beats buying (62)
        12: {"high": 23, "low": 20},   # tomato
        13: {"high": 90, "low": 80},   # uncooked pizza
        14: {"high": 120, "low": 110},
    })
    rows, _ = profit.evaluate_all(recipes, items, store)
    by_id = {r["recipe_id"]: r for r in rows}
    # uncooked pizza = cheese (craft 13 < buy 62) + tomato (buy 23) = 36
    assert by_id["uncooked_pizza"]["cost"] == 36
    # plain pizza's material must use that same recursive 36, not the
    # buy-only 85 (62 + 23) the old single-level pass produced
    assert by_id["plain_pizza"]["materials"][0]["craft"] == 36
    assert by_id["plain_pizza"]["cost"] == 36
