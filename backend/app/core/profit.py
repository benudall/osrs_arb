import math

from .. import config


def ge_tax(sell_price: int) -> int:
    """Grand Exchange tax on one item sold at sell_price.

    2% of the sale price, rounded down; items selling below 50 gp are
    effectively exempt (floor would be < 1 coin), capped at 5,000,000 gp per item.
    """
    if sell_price is None or sell_price < config.GE_TAX_EXEMPT_BELOW:
        return 0
    return min(math.floor(sell_price * config.GE_TAX_RATE), config.GE_TAX_CAP)


def _side(price_resolved, mode: str, kind: str):
    """price_resolved: store.resolve() output. Returns (value, stale, source, vol, vol_src)."""
    if kind == "buy":
        side = "high" if mode == "conservative" else "low"
        vol = "high_vol" if mode == "conservative" else "low_vol"
    else:
        side = "low" if mode == "conservative" else "high"
        vol = "low_vol" if mode == "conservative" else "high_vol"
    value, stale, source = price_resolved[side]
    v, vsrc = price_resolved[vol]
    return value, stale, source, v, vsrc


def evaluate_recipe(recipe: dict, item_map: dict, store, mode: str = "conservative",
                    craft_costs: dict | None = None) -> dict | None:
    """Compute one recipe row. Returns None if any needed price is missing.

    recipe: {id, skill, level, members, product: {item_id, qty},
             materials: [{item_id, qty}], fee, note}
    item_map: {item_id: {name, members, buy_limit, value}}
    store: PriceStore
    """
    prod_info = item_map.get(recipe["product"]["item_id"])
    if prod_info is None:
        return None
    prod_res = store.resolve(recipe["product"]["item_id"])
    if prod_res is None:
        return None

    sell_price, sell_stale, sell_src, sell_vol, sell_vol_src = _side(prod_res, mode, "sell")
    if sell_price is None:
        return None
    prod_buy, prod_buy_stale, prod_buy_src, prod_buy_vol, _ = _side(prod_res, mode, "buy")

    materials = []
    cost = float(recipe.get("fee", 0))
    min_mat_vol = None
    for m in recipe["materials"]:
        info = item_map.get(m["item_id"])
        if info is None:
            return None
        res = store.resolve(m["item_id"])
        if res is None:
            return None
        buy_price, buy_stale, buy_src, buy_vol, buy_vol_src = _side(res, mode, "buy")
        mat_sell, _, _, _, _ = _side(res, mode, "sell")
        if buy_price is None:
            return None
        craft_unit = round(craft_costs[m["item_id"]]) if craft_costs and m["item_id"] in craft_costs else None
        # cheapest acquisition for this material: buy at GE price, or craft it if that is cheaper
        chosen = craft_unit if craft_unit is not None and craft_unit < buy_price else buy_price
        materials.append({
            "id": m["item_id"],
            "name": info["name"],
            "image_url": info.get("image_url"),
            "qty": m["qty"],
            "price": buy_price,
            "stale": buy_stale,
            "source": buy_src,
            "vol": buy_vol,
            "sell": mat_sell,
            "sell_tax": ge_tax(mat_sell) if mat_sell is not None else 0,
            "craft": craft_unit,
        })
        cost += chosen * m["qty"]
        # how many crafts per 5m does this material's buy-side volume support?
        supported = buy_vol / m["qty"] if m["qty"] > 0 else float('inf')
        min_mat_vol = supported if min_mat_vol is None else min(min_mat_vol, supported)

    gross = sell_price * recipe["product"]["qty"]
    tax_total = ge_tax(sell_price) * recipe["product"]["qty"]
    net = gross - tax_total - cost
    net_pct = round(net / cost * 100, 1) if cost > 0 else None

    # 4h buy-limit cap: limited by every material and the product itself
    max_crafts = None
    limited = False
    for m in recipe["materials"]:
        limit = item_map[m["item_id"]]["buy_limit"]
        if limit is None:
            limited = True
            continue
        c = limit // m["qty"]
        max_crafts = c if max_crafts is None else min(max_crafts, c)
    prod_limit = prod_info["buy_limit"]
    if prod_limit is None:
        limited = True
    else:
        c = prod_limit // recipe["product"]["qty"]
        max_crafts = c if max_crafts is None else min(max_crafts, c)
    if max_crafts is None:
        max_crafts = 0
    net_4h = None if (limited or max_crafts == 0) else net * max_crafts

    volume = int(min(sell_vol, min_mat_vol)) if min_mat_vol is not None else int(sell_vol)

    tools_out = []
    for t in recipe.get("tools") or []:
        entry = {"id": t.get("item_id"), "name": t.get("name"), "image_url": None, "buy": None, "sell": None, "tax": 0}
        if entry["id"] and entry["id"] in item_map:
            info = item_map[entry["id"]]
            entry["image_url"] = info.get("image_url")
            res = store.resolve(entry["id"])
            if res:
                entry["buy"] = res["high"][0]
                entry["sell"] = res["low"][0]
                entry["tax"] = ge_tax(res["low"][0]) if res["low"][0] is not None else 0
        tools_out.append(entry)

    return {
        "recipe_id": recipe["id"],
        "skill": recipe["skill"],
        "level": recipe["level"],
        "extra_skills": recipe.get("extra_skills") or [],
        "xp": recipe.get("xp", 0),
        "members": recipe["members"],
        "product": {
            "id": prod_info["id"],
            "name": prod_info["name"],
            "image_url": prod_info.get("image_url"),
            "qty": recipe["product"]["qty"],
            "price": sell_price,
            "buy": prod_buy,
            "value": prod_info.get("value"),
            "stale": sell_stale,
            "source": sell_src,
            "vol": sell_vol,
        },
        "materials": materials,
        "fee": recipe.get("fee", 0),
        "cost": round(cost),
        "gross": gross,
        "tax": tax_total,
        "net": round(net),
        "net_pct": net_pct,
        "volume": max(volume, 0),
        "max_crafts_4h": max_crafts,
        "net_4h": round(net_4h) if net_4h is not None else None,
        "mode": mode,
        "note": recipe.get("note"),
        "tools": tools_out,
        "facilities": recipe.get("facilities") or [],
    }
