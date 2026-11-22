"""Bake backend/data/recipes.json (item names) into ../data/recipes.json
(item ids + display metadata) for the static GitHub Pages site.

The output is self-contained: the browser needs no /mapping fetch at runtime —
every referenced item carries name, image URL, buy limit, value and members
flag. Prices still come live from the wiki prices API (CORS-open).

Re-run whenever recipes.json or the mapping changes:
    cd backend && python scripts/bake_static.py

Usage (from backend/):  python scripts/bake_static.py [--force-mapping]
"""
import json
import sys
import time

sys.path.insert(0, ".")

import config  # noqa: E402
import itemdata  # noqa: E402
import recipes as recipes_mod  # noqa: E402


def main() -> int:
    force = "--force-mapping" in sys.argv
    mapping = itemdata.fetch_mapping(force=force)
    name_to_id, item_map = itemdata.index_mapping(mapping)

    raw = recipes_mod.load_recipe_file(config.RECIPES_PATH)
    ok, struct_errors = recipes_mod.validate(raw)
    for e in struct_errors:
        print(f"STRUCTURAL: {e}")
    resolved, unknown = recipes_mod.resolve_names(ok, name_to_id)
    for r in resolved:
        r["members"] = recipes_mod.compute_members(r["product"]["item_id"], r["materials"], item_map)

    # every item referenced by any recipe (+ Nature rune for client-side alch math)
    used = set()
    for r in resolved:
        used.add(r["product"]["item_id"])
        used.update(m["item_id"] for m in r["materials"])
        used.update(t["item_id"] for t in r["tools"] if t["item_id"] is not None)
    nature_id = name_to_id.get("Nature rune")
    if nature_id is not None:
        used.add(nature_id)

    missing_meta = [i for i in used if i not in item_map]
    if missing_meta:
        print(f"ERROR: {len(missing_meta)} referenced items missing from /mapping: {missing_meta[:10]}")
        return 1

    items_out = {
        str(iid): {
            "name": item_map[iid]["name"],
            "image": item_map[iid]["image_url"],
            "limit": item_map[iid]["buy_limit"],
            "value": item_map[iid]["value"],
            "members": item_map[iid]["members"],
        }
        for iid in sorted(used)
    }
    recipes_out = [
        {
            "id": r["id"],
            "skill": r["skill"],
            "level": r["level"],
            "extra_skills": r.get("extra_skills") or [],
            "xp": r["xp"],
            "members": r["members"],
            "product": {"id": r["product"]["item_id"], "qty": r["product"]["qty"]},
            "materials": [{"id": m["item_id"], "qty": m["qty"]} for m in r["materials"]],
            "fee": r.get("fee", 0),
            "note": r.get("note"),
            "tools": [{"id": t["item_id"], "name": t["name"]} for t in r["tools"]],
            "facilities": r.get("facilities") or [],
        }
        for r in resolved
    ]
    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "items": items_out,
        "recipes": recipes_out,
    }

    config.SITE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.SITE_DATA_PATH.write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"baked {len(recipes_out)} recipes, {len(items_out)} items -> {config.SITE_DATA_PATH}")
    if unknown:
        print(f"unknown item names skipped: {unknown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
