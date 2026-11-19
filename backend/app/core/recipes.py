"""Load, validate, and seed the curated recipe database.

recipes.json stores item NAMES (human-reviewable); seeding resolves them to
item ids via the /mapping data in the items table.
"""
import json
import logging

from ..db import dao

log = logging.getLogger(__name__)

REQUIRED_KEYS = {"id", "skill", "level", "members", "product", "materials", "xp"}


def load_recipe_file(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    recipes = data.get("recipes", [])
    if not recipes:
        raise ValueError(f"{path} contains no recipes")
    return recipes


def validate(raw: list[dict]) -> tuple[list[dict], list[str]]:
    """Structural validation (no item resolution). Returns (ok, errors)."""
    ok, errors = [], []
    seen_ids = set()
    for r in raw:
        rid = r.get("id", "<missing id>")
        missing = REQUIRED_KEYS - set(r)
        if missing:
            errors.append(f"{rid}: missing keys {sorted(missing)}")
            continue
        if r["id"] in seen_ids:
            errors.append(f"{rid}: duplicate id")
            continue
        seen_ids.add(r["id"])
        if not isinstance(r["level"], int) or not (1 <= r["level"] <= 99):
            errors.append(f"{rid}: level must be int 1-99")
            continue
        xp = r["xp"]
        if isinstance(xp, bool) or not isinstance(xp, (int, float)) or xp < 0:
            errors.append(f"{rid}: xp must be a number >= 0 (OSRS wiki value per craft)")
            continue
        if not r["product"].get("item") or not isinstance(r["product"].get("qty"), int) or r["product"]["qty"] < 1:
            errors.append(f"{rid}: bad product")
            continue
        if not r["materials"] or not all(
            isinstance(m.get("qty"), int) and m["qty"] > 0 and m.get("item") for m in r["materials"]
        ):
            errors.append(f"{rid}: bad materials")
            continue
        ok.append(r)
    return ok, errors


def infer_extras(skill, product_name, materials, fee):
    """Guess tools + facilities for a recipe (used when not hand-curated)."""
    tools, facilities = [], []
    prod = product_name.lower()
    mats = [m["item"].lower() for m in materials]
    if skill == "smithing":
        if prod.endswith(" bar"):
            facilities.append("Furnace")
        elif "cannonball" in prod:
            tools.append("Ammo mould")
            facilities.append("Furnace")
        else:
            tools.append("Hammer")
            facilities.append("Anvil")
    elif skill == "cooking":
        if any(m.startswith("raw ") for m in mats):
            facilities.append("Cooking range or fire")
    elif skill == "crafting":
        if fee > 0 or any("hide" in m for m in mats):
            facilities.append("Tanner")
        if any(m.startswith(("gold bar", "silver bar")) for m in mats):
            facilities.append("Furnace")
            mould = {"ring": "Ring mould", "necklace": "Necklace mould",
                     "amulet": "Amulet mould", "bracelet": "Bracelet mould",
                     "symbol": "Holy mould", "emblem": "Holy mould",
                     "tiara": "Tiara mould", "sickle": "Silver sickle mould"}
            for key, mould_name in mould.items():
                if key in prod:
                    tools.append(mould_name)
                    break
        if any("glass" in m for m in mats):
            facilities.append("Furnace")
        if "flax" in mats:
            facilities.append("Spinning wheel")
        if any("leather" in m for m in mats):
            tools.append("Needle")
    elif skill == "fletching":
        if any(m == "logs" or m.endswith("logs") for m in mats):
            tools.append("Knife")
    return tools, facilities


def compute_members(product_item_id, materials, item_map):
    """A recipe is members-only if the product is a members item or any
    ingredient is a members item (e.g. steel arrowtips smithed from f2p
    steel bars, rope from members-only hair). All six recipe skills here
    (smithing/crafting/cooking/fletching/herblore/magic) are f2p skills;
    membership is decided by the items, not the skill - e.g. jug of wine
    and lvl-1 amulet/ring enchants are f2p."""
    prod = item_map.get(product_item_id)
    if prod and prod["members"]:
        return True
    return any(
        (item_map.get(m["item_id"]) or {}).get("members", False) for m in materials
    )


def resolve_names(raw: list[dict], name_to_id: dict) -> tuple[list[dict], list[str]]:
    """Resolve item names to ids. Returns (resolved, unknown_names)."""
    resolved, unknown = [], set()
    for r in raw:
        try:
            product = {"item_id": name_to_id[r["product"]["item"]], "qty": r["product"]["qty"]}
            materials = [{"item_id": name_to_id[m["item"]], "qty": m["qty"]} for m in r["materials"]]
        except KeyError as e:
            unknown.add(str(e.args[0]))
            continue
        tools = r.get("tools") or []
        facilities = r.get("facilities") or []
        if not tools or not facilities:
            inf_tools, inf_fac = infer_extras(r["skill"], r["product"]["item"], r["materials"], r.get("fee", 0))
            tools = tools or inf_tools
            facilities = facilities or inf_fac
        resolved.append({
            "id": r["id"],
            "skill": r["skill"],
            "level": r["level"],
            "xp": r["xp"],
            "members": bool(r["members"]),
            "product": product,
            "materials": materials,
            "fee": int(r.get("fee", 0)),
            "note": r.get("note"),
            "tools": [{"item_id": name_to_id.get(n), "name": n} for n in tools],
            "facilities": facilities,
        })
    return resolved, sorted(unknown)


def seed(db, recipes_path) -> dict:
    """Validate + resolve + write recipes to DB. Returns a report.

    The members flag in recipes.json is documentation only - the DB stores a
    computed flag (product or any ingredient is a members item)."""
    raw = load_recipe_file(recipes_path)
    ok, struct_errors = validate(raw)
    for e in struct_errors:
        log.error("recipe %s", e)
    name_to_id = dao.get_name_to_id(db)
    if not name_to_id:
        raise RuntimeError("items table empty - fetch /mapping before seeding recipes")
    item_map = dao.get_item_map(db)
    resolved, unknown = resolve_names(ok, name_to_id)
    for r in resolved:
        r["members"] = compute_members(r["product"]["item_id"], r["materials"], item_map)
    dao.replace_recipes(db, resolved)
    return {
        "total_in_file": len(raw),
        "seeded": len(resolved),
        "skipped_structural": len(struct_errors),
        "unknown_items": unknown,
        "structural_errors": struct_errors,
    }
