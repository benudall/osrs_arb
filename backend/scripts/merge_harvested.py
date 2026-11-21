"""Merge harvested wiki recipes into data/recipes.json.

- curated recipes always win (same product item id)
- product/material names resolved against the items table (from /mapping)
- members flag: harvested value if present, else the product item's flag
- one recipe per product item id (first wins)
- unknown products/materials are skipped and reported

Usage (from backend/):  python scripts/merge_harvested.py [--dry-run]
"""
import json
import re
import sys

sys.path.insert(0, ".")

from app import config  # noqa: E402
from app.core import recipes as recipes_mod  # noqa: E402
from app.db import dao  # noqa: E402
from app.db.sqlite import Database  # noqa: E402


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "recipe"


DOSE_SUFFIXES = ["", "(3)", "(2)", "(4)", "(1)"]


def resolve_item(name, name_to_id, lower_map=None):
    """Exact, dose suffixes, highest-charge variant, then case-insensitive
    ('Raw Bass' from wiki vs 'Raw bass' in the GE mapping)."""
    for suffix in DOSE_SUFFIXES:
        candidate = name + suffix
        if candidate in name_to_id:
            return candidate
    prefix = name + "("
    variants = [n for n in name_to_id if n.startswith(prefix)]
    if variants:
        def charge(n):
            m = re.search(r"\((\d+)\)$", n)
            return int(m.group(1)) if m else 0
        return max(variants, key=charge)  # highest charge/dose, numeric (not lexicographic)
    if lower_map:
        hit = lower_map.get(name.lower())
        if hit is not None:
            return hit
    return None


def main():
    dry = "--dry-run" in sys.argv
    db = Database(config.DB_PATH)
    items = dao.get_item_map(db)  # id -> {name, members, buy_limit}
    name_to_id = {v["name"]: k for k, v in items.items()}
    lower_map = {}
    for n in name_to_id:
        lower_map.setdefault(n.lower(), n)

    curated_doc = json.loads(config.RECIPES_PATH.read_text(encoding="utf-8"))
    curated = curated_doc["recipes"]
    curated_products = {name_to_id[r["product"]["item"]] for r in curated
                        if r["product"]["item"] in name_to_id}

    harvested = json.loads(
        (config.RECIPES_PATH.parent / "harvested_raw.json").read_text(encoding="utf-8")
    )["recipes"]

    # wiki cooking table uses generic names; GE items differ
    RAW_OVERRIDES = {"Raw meat": "Raw beef", "Raw Sinew": "Raw beef",
                     "Raw Cooked meat": "Raw beef", "Raw Cooked chicken": "Raw chicken",
                     "Raw Cooked rabbit": "Raw rabbit"}
    CURATED_PRODUCTS = {name_to_id[r["product"]["item"]] for r in curated
                        if r["product"]["item"] in name_to_id}

    added, skipped = [], {"unknown_product": 0, "unknown_material": 0, "dup": 0,
                          "self_loop": 0, "bad_level": 0}
    skip_detail = {}
    seen_products = set(CURATED_PRODUCTS)
    for r in harvested:
        prod_name = r["product"]["item"]
        def skip(reason):
            skipped[reason] += 1
            key = (r["skill"], reason)
            if len(skip_detail.setdefault(key, [])) < 3:
                skip_detail[key].append(prod_name)
        resolved = resolve_item(prod_name, name_to_id, lower_map)
        if resolved is None:
            skip("unknown_product")
            continue
        prod_name = resolved
        prod_id = name_to_id[prod_name]
        if prod_id in seen_products:
            skip("dup")
            continue
        level = r.get("level")
        if not isinstance(level, int) or not (1 <= level <= 99):
            skip("bad_level")
            continue
        mats, bad, bad_item = [], False, None
        for m in r["materials"]:
            m_name = RAW_OVERRIDES.get(m["item"], m["item"])
            m_resolved = resolve_item(m_name, name_to_id, lower_map)
            if m_resolved is None:
                bad, bad_item = True, m["item"]
                break
            mid = name_to_id[m_resolved]
            if mid == prod_id:
                bad, bad_item = True, m["item"]
                break
            mats.append({"item": m_resolved, "qty": m["qty"]})
        if bad:
            skip("unknown_material")
            if bad_item and len(skip_detail[(r["skill"], "unknown_material")]) <= 3:
                skip_detail[(r["skill"], "unknown_material")].append(f"  [via {bad_item}]")
            continue
        if not mats:
            skipped["unknown_material"] += 1
            continue
        members = r.get("members")
        if members is None:
            members = items[prod_id]["members"]
        seen_products.add(prod_id)
        rid = slug(prod_name)
        base_rid = rid
        n = 2
        taken = {a["id"] for a in added} | {r["id"] for r in curated}
        while rid in taken:
            rid = f"{base_rid}_{n}"
            n += 1
        added.append({
            "id": rid,
            "skill": r["skill"],
            "level": level,
            "members": bool(members),
            "product": {"item": prod_name, "qty": r["product"]["qty"]},
            "materials": mats,
            "fee": 0,
            "note": None,
            "tools": r.get("tools") or [],
        })

    print(f"curated kept: {len(curated)}")
    print(f"harvested: {len(harvested)} -> added: {len(added)} | skipped: {skipped}")
    for (skill, reason), examples in sorted(skip_detail.items()):
        print(f"  {skill}/{reason}: e.g. {examples}")
    by_skill = {}
    for r in added:
        by_skill[r["skill"]] = by_skill.get(r["skill"], 0) + 1
    print("added by skill:", by_skill)

    if dry:
        for r in added[:15]:
            print(" ", r["id"], f"lvl {r['level']}", "<-",
                  [(m["item"], m["qty"]) for m in r["materials"]])
        return 0

    merged = dict(curated_doc)
    merged["version"] = curated_doc.get("version", 1) + 1
    merged["recipes"] = curated + added
    config.RECIPES_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"wrote {len(merged['recipes'])} recipes -> {config.RECIPES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
