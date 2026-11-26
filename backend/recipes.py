"""Recipe loading, validation, and name resolution (DB-free).

Recipes are stored one <skill>.json per skill under data/recipes/ (item
NAMES, human-reviewable); baking resolves them to item ids via the /mapping
data. Used by scripts/bake_static.py and scripts/merge_harvested.py.
"""
import json
import logging
import pathlib

log = logging.getLogger(__name__)

REQUIRED_KEYS = {"id", "skill", "level", "members", "product", "materials", "xp"}


def load_recipes(recipes_dir) -> list[dict]:
    """Load and concatenate recipes from every <skill>.json in recipes_dir.

    Files starting with '_' (e.g. _meta.json) are skipped. Recipes keep their
    file order, so the concatenation stays grouped by skill.
    """
    recipes_dir = pathlib.Path(recipes_dir)
    recipes: list[dict] = []
    for path in sorted(recipes_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        batch = data["recipes"] if isinstance(data, dict) else data
        if not batch:
            raise ValueError(f"{path} contains no recipes")
        recipes.extend(batch)
    if not recipes:
        raise ValueError(f"{recipes_dir} contains no recipes")
    return recipes


def load_meta(recipes_dir) -> dict:
    """Load _meta.json (version/source notes) from recipes_dir; {} if absent."""
    path = pathlib.Path(recipes_dir) / "_meta.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_recipes(recipes_dir, recipes: list[dict], meta: dict | None = None) -> None:
    """Group recipes by skill and write one <skill>.json per skill.

    Each file is {"skill": ..., "recipes": [...]}. Stale skill files from
    removed skills are deleted. meta (optional) replaces _meta.json.
    """
    recipes_dir = pathlib.Path(recipes_dir)
    recipes_dir.mkdir(parents=True, exist_ok=True)
    by_skill: dict[str, list[dict]] = {}
    for r in recipes:
        by_skill.setdefault(r["skill"], []).append(r)
    for skill, batch in sorted(by_skill.items()):
        path = recipes_dir / f"{skill}.json"
        path.write_text(
            json.dumps({"skill": skill, "recipes": batch}, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    for path in recipes_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        if path.stem not in by_skill:
            path.unlink()
    if meta is not None:
        (recipes_dir / "_meta.json").write_text(
            json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )


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
        if not isinstance(r["product"], dict) or not r["product"].get("item") \
                or not isinstance(r["product"].get("qty"), int) or r["product"]["qty"] < 1:
            errors.append(f"{rid}: bad product")
            continue
        if not isinstance(r["materials"], list) or not r["materials"] or not all(
            isinstance(m, dict) and isinstance(m.get("qty"), int) and m["qty"] > 0 and m.get("item")
            for m in r["materials"]
        ):
            errors.append(f"{rid}: bad materials")
            continue
        if "extra_skills" in r:
            if not isinstance(r["extra_skills"], list):
                errors.append(f"{rid}: extra_skills must be a list")
                continue
            for es in r["extra_skills"]:
                if not isinstance(es, dict) or "skill" not in es or "level" not in es:
                    errors.append(f"{rid}: extra_skills elements must be dicts with 'skill' and 'level'")
                    continue
                if not isinstance(es["level"], int) or not (1 <= es["level"] <= 99):
                    errors.append(f"{rid}: extra_skill level must be int 1-99")
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
        if any(m.startswith("uncut ") for m in mats):
            tools.append("Chisel")  # gem cutting (opal through zenyte)
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
            "extra_skills": r.get("extra_skills", []),
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
