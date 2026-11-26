"""Bake backend/data/recipes/<skill>.json (item names) into the static files
served by the GitHub Pages site:

  data/items.json              {generated, items: {id -> name/image/limit/value/members}}
  data/recipes/<skill>.json    bare array of resolved recipes for that skill
  data/recipes/index.json      {generated, skills: [...]} manifest for the loader

The output is self-contained: the browser needs no /mapping fetch at runtime —
every referenced item carries name, image URL, buy limit, value and members
flag. Prices still come live from the wiki prices API (CORS-open).

Re-run whenever the recipe files or the mapping change:
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

    raw = recipes_mod.load_recipes(config.RECIPES_DIR)
    ok, struct_errors = recipes_mod.validate(raw)
    for e in struct_errors:
        print(f"STRUCTURAL: {e}")

    # Names missing from /mapping (items with no GE price history) fall back to
    # their OSRS wiki infoboxes for id/value/members/image, so recipes can
    # reference unpriced items and still render (craft cost partial, alch ok).
    ref_names = set()
    for r in ok:
        ref_names.add(r["product"]["item"])
        ref_names.update(m["item"] for m in r["materials"])
        ref_names.update(t for t in r.get("tools") or [])
    missing_names = sorted(n for n in ref_names if n not in name_to_id)
    wiki_meta = itemdata.fetch_wiki_meta(missing_names) if missing_names else {}
    fallback_used = []
    for n in missing_names:
        meta = wiki_meta.get(n)
        if not meta or not meta.get("id"):
            continue
        mid = int(meta["id"])
        if mid not in item_map:
            item_map[mid] = itemdata.fallback_item_map_entry(meta, display_name=n)
        name_to_id[n] = mid
        fallback_used.append(n)
    if fallback_used:
        print(f"wiki-meta fallback ({len(fallback_used)}): " + ", ".join(fallback_used))

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
    generated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    skills = sorted({r["skill"] for r in recipes_out})

    config.SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.SITE_ITEMS_PATH.write_text(
        json.dumps({"generated": generated, "items": items_out}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    config.SITE_RECIPES_DIR.mkdir(parents=True, exist_ok=True)
    by_skill: dict[str, list] = {}
    for r in recipes_out:
        by_skill.setdefault(r["skill"], []).append(r)
    for skill, batch in sorted(by_skill.items()):
        (config.SITE_RECIPES_DIR / f"{skill}.json").write_text(
            json.dumps(batch, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    for path in config.SITE_RECIPES_DIR.glob("*.json"):
        if path.stem not in by_skill:
            path.unlink()
    config.SITE_RECIPES_INDEX.write_text(
        json.dumps({"generated": generated, "skills": skills}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"baked {len(recipes_out)} recipes ({len(skills)} skills), {len(items_out)} items "
          f"-> {config.SITE_ITEMS_PATH}, {config.SITE_RECIPES_DIR}/")
    if unknown:
        print(f"unknown item names skipped: {unknown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
