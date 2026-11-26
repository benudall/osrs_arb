"""Add missing Crafting recipes curated from the OSRS wiki Crafting/Experience
table (https://oldschool.runescape.wiki/w/Crafting/Experience_table).

Adds, per the wiki table:
  - amulet stringing (ball of wool) for every gem/jewellery amulet
  - symbol stringing (Unblessed/Unpowered symbol) and the Pre-nature amulet
  - pottery chain (unfired wares from soft clay -> fired wares)
  - molten glass (sand + soda ash) and the missing glassblowing wares
  - spiky vambraces, strung rabbit foot, slayer ring (+eternal), slayer helmet
  - misc GE-tradeable crafts: clockwork, watch, limestone brick, toys,
    lunar leather gear, crossbow string, broodoo shields, colossal pouch
  - endgame combine crafts with tradeable inputs: catacomb icons/rings,
    Masori (f), Armadylean plates, serpentine helm, toxic staff, tridents,
    noxious halberd, purging staff, bone staff, celestial signet, crystal gear,
    Amulet of rancour, Necklace of rupture, Accursed sceptre

Excluded by design: quest/event-locked items, multi-source variants (dyed
capes, heraldic helms/kiteshields, banners), String Jewellery / Superglass
Make / Spin Flax spell rows (Magic skill), items without tradeable inputs
(vestige-free intermediates), tools/POH construction pieces, Barbarian pyre
(Firemaking) and blank rune rows.

Usage (from backend/):  python scripts/add_crafting.py [--dry-run]
"""
import json
import sys

sys.path.insert(0, ".")
import config  # noqa: E402
import itemdata  # noqa: E402
import recipes as recipes_mod  # noqa: E402
import urllib.request  # noqa: E402

# (id, product, level, xp, materials, note) — xp from the wiki XP table.
C = [
    # --- amulet stringing (ball of wool) ---
    ("opal_amulet", "Opal amulet", 1, 4.0, [("Opal amulet (u)", 1), ("Ball of wool", 1)], None),
    ("jade_amulet", "Jade amulet", 1, 4.0, [("Jade amulet (u)", 1), ("Ball of wool", 1)], None),
    ("topaz_amulet", "Topaz amulet", 1, 4.0, [("Topaz amulet (u)", 1), ("Ball of wool", 1)], None),
    ("gold_amulet", "Gold amulet", 1, 4.0, [("Gold amulet (u)", 1), ("Ball of wool", 1)], None),
    ("emerald_amulet", "Emerald amulet", 1, 4.0, [("Emerald amulet (u)", 1), ("Ball of wool", 1)], None),
    ("ruby_amulet", "Ruby amulet", 1, 4.0, [("Ruby amulet (u)", 1), ("Ball of wool", 1)], None),
    ("diamond_amulet", "Diamond amulet", 1, 4.0, [("Diamond amulet (u)", 1), ("Ball of wool", 1)], None),
    ("dragonstone_amulet", "Dragonstone amulet", 1, 4.0, [("Dragonstone amulet (u)", 1), ("Ball of wool", 1)], None),
    ("onyx_amulet", "Onyx amulet", 1, 4.0, [("Onyx amulet (u)", 1), ("Ball of wool", 1)], None),
    ("zenyte_amulet", "Zenyte amulet", 1, 4.0, [("Zenyte amulet (u)", 1), ("Ball of wool", 1)], None),
    # --- symbol stringing / magic string ---
    ("unblessed_symbol", "Unblessed symbol", 1, 4.0, [("Unstrung symbol", 1), ("Ball of wool", 1)], None),
    ("unpowered_symbol", "Unpowered symbol", 1, 4.0, [("Unstrung emblem", 1), ("Ball of wool", 1)], None),
    ("pre_nature_amulet", "Pre-nature amulet", 1, 4.0,
     [("Emerald amulet (u)", 1), ("Magic string", 1)], None),
    # --- spiky vambraces (kebbit claws + vambraces) ---
    ("spiky_vambraces", "Spiky vambraces", 32, 6.0, [("Kebbit claws", 1), ("Leather vambraces", 1)], None),
    ("green_spiky_vambraces", "Green spiky vambraces", 32, 5.0,
     [("Kebbit claws", 1), ("Green d'hide vambraces", 1)], None),
    ("blue_spiky_vambraces", "Blue spiky vambraces", 32, 6.0,
     [("Kebbit claws", 1), ("Blue d'hide vambraces", 1)], None),
    ("red_spiky_vambraces", "Red spiky vambraces", 32, 5.8,
     [("Kebbit claws", 1), ("Red d'hide vambraces", 1)], None),
    ("black_spiky_vambraces", "Black spiky vambraces", 32, 6.0,
     [("Kebbit claws", 1), ("Black d'hide vambraces", 1)], None),
    # --- hunter / slayer strings ---
    ("strung_rabbit_foot", "Strung rabbit foot", 37, 4.0, [("Rabbit foot", 1), ("Ball of wool", 1)], None),
    # --- pottery (soft clay -> unfired -> fired) ---
    ("unfired_pot", "Unfired pot", 1, 6.3, [("Soft clay", 1)], None),
    ("pot", "Pot", 1, 6.3, [("Unfired pot", 1)], None),
    ("unfired_cup", "Unfired cup", 3, 8.5, [("Soft clay", 1)], None),
    ("empty_cup", "Empty cup", 1, 8.5, [("Unfired cup", 1)], None),
    ("unfired_pie_dish", "Unfired pie dish", 7, 15.0, [("Soft clay", 1)], None),
    ("pie_dish", "Pie dish", 1, 10.0, [("Unfired pie dish", 1)], None),
    ("unfired_bowl", "Unfired bowl", 8, 18.0, [("Soft clay", 1)], None),
    ("bowl", "Bowl", 1, 15.0, [("Unfired bowl", 1)], None),
    ("unfired_plant_pot", "Unfired plant pot", 19, 20.0, [("Soft clay", 1)], None),
    ("empty_plant_pot", "Empty plant pot", 1, 17.5, [("Unfired plant pot", 1)], None),
    ("unfired_pot_lid", "Unfired pot lid", 25, 20.0, [("Soft clay", 1)], None),
    ("pot_lid", "Pot lid", 1, 20.0, [("Unfired pot lid", 1)], None),
    # --- glass: molten glass + missing glassblowing wares ---
    ("molten_glass", "Molten glass", 1, 20.0, [("Bucket of sand", 1), ("Soda ash", 1)], None),
    ("empty_light_orb", "Empty light orb", 87, 70.0, [("Molten glass", 1)], None),
    ("bullseye_lantern_empty", "Bullseye lantern (empty)", 49, 0.0,
     [("Bullseye lantern (unf)", 1), ("Lantern lens", 1)],
     "Bullseye lantern (unf) is a Smithing product (49 Smithing)."),
    # --- misc silver/steel crafts ---
    ("clockwork", "Clockwork", 8, 15.0, [("Steel bar", 1)], None),
    ("limestone_brick", "Limestone brick", 12, 6.0, [("Limestone", 1)], None),
    # --- toys ---
    ("toy_soldier", "Toy soldier", 13, 15.0, [("Clockwork", 1), ("Plank", 1)], None),
    ("toy_doll", "Toy doll", 18, 15.0, [("Clockwork", 1), ("Plank", 1)], None),
    ("toy_mouse", "Toy mouse", 33, 15.0, [("Clockwork", 1), ("Plank", 1)], None),
    ("toy_cat", "Toy cat", 85, 15.0, [("Clockwork", 1), ("Plank", 1)], None),
    ("white_toy_horsey", "White toy horsey", 10, 15.0, [("Plank", 1)], None),
    ("brown_toy_horsey", "Brown toy horsey", 10, 15.0, [("Plank", 1)], None),
    ("grey_toy_horsey", "Grey toy horsey", 10, 15.0, [("Plank", 1)], None),
    ("black_toy_horsey", "Black toy horsey", 10, 15.0, [("Plank", 1)], None),
    ("wooden_cat", "Wooden cat", 16, 15.0, [("Plank", 1), ("Fur", 1)], None),
    # --- lunar leather gear ---
    ("lunar_boots", "Lunar boots", 61, 25.0, [("Suqah leather", 1), ("Thread", 1)], None),
    ("lunar_gloves", "Lunar gloves", 61, 25.0, [("Suqah leather", 1), ("Thread", 1)], None),
    ("lunar_legs", "Lunar legs", 61, 30.0, [("Suqah leather", 1), ("Thread", 1)], None),
    ("lunar_torso", "Lunar torso", 61, 35.0, [("Suqah leather", 1), ("Thread", 1)], None),
    # --- misc tradeable crafts ---
    ("crossbow_string", "Crossbow string", 10, 15.0, [("Sinew", 1)], None),
    ("broodoo_shield_combat", "Broodoo shield (combat)", 35, 100.0,
     [("Snakeskin", 2), ("Tribal mask (combat)", 1), ("Bronze nails", 8)], None),
    ("broodoo_shield_disease", "Broodoo shield (disease)", 35, 100.0,
     [("Snakeskin", 2), ("Tribal mask (disease)", 1), ("Bronze nails", 8)], None),
    ("broodoo_shield_poison", "Broodoo shield (poison)", 35, 100.0,
     [("Snakeskin", 2), ("Tribal mask (poison)", 1), ("Bronze nails", 8)], None),
    # --- catacomb icons & rings (tradeable inputs) ---
    ("archer_icon", "Archer icon", 80, 400.0, [("Archers ring", 1)], None),
    ("berserker_icon", "Berserker icon", 80, 400.0, [("Berserker ring", 1)], None),
    ("seers_icon", "Seers icon", 80, 400.0, [("Seers ring", 1)], None),
    ("warrior_icon", "Warrior icon", 80, 400.0, [("Warrior ring", 1)], None),
    ("ultor_icon", "Ultor icon", 80, 0.0,
     [("Ultor vestige", 1), ("Berserker icon", 1), ("Blood rune", 500)], None),
    ("magus_icon", "Magus icon", 80, 0.0,
     [("Magus vestige", 1), ("Seers icon", 1), ("Blood rune", 500)], None),
    ("bellator_icon", "Bellator icon", 80, 0.0,
     [("Bellator vestige", 1), ("Warrior icon", 1), ("Blood rune", 500)], None),
    ("venator_icon", "Venator icon", 80, 0.0,
     [("Venator vestige", 1), ("Archer icon", 1), ("Blood rune", 500)], None),
    ("ultor_ring", "Ultor ring", 80, 2500.0, [("Ultor icon", 1), ("Chromium ingot", 3)], None),
    ("magus_ring", "Magus ring", 80, 2500.0, [("Magus icon", 1), ("Chromium ingot", 3)], None),
    ("bellator_ring", "Bellator ring", 80, 2500.0, [("Bellator icon", 1), ("Chromium ingot", 3)], None),
    ("venator_ring", "Venator ring", 80, 2500.0, [("Venator icon", 1), ("Chromium ingot", 3)], None),
    # --- Masori (f) + Armadylean plates ---
    ("armadylean_plate_helm", "Armadylean plate", 90, 210.0, [("Armadyl helmet", 1)], None),
    ("armadylean_plate_chest", "Armadylean plate", 90, 840.0, [("Armadyl chestplate", 1)], None),
    ("armadylean_plate_skirt", "Armadylean plate", 90, 630.0, [("Armadyl chainskirt", 1)], None),
    ("masori_body_f", "Masori body (f)", 90, 3320.0, [("Masori body", 1), ("Armadylean plate", 4)], None),
    ("masori_chaps_f", "Masori chaps (f)", 90, 2490.0, [("Masori chaps", 1), ("Armadylean plate", 3)], None),
    ("masori_mask_f", "Masori mask (f)", 90, 830.0, [("Masori mask", 1), ("Armadylean plate", 1)], None),
    # --- boss combine crafts (tradeable inputs) ---
    ("serpentine_helm_uncharged", "Serpentine helm (uncharged)", 52, 120.0,
     [("Serpentine visage", 1)], None),
    ("trident_uncharged", "Uncharged trident", 59, 0.0,
     [("Uncharged trident", 1), ("Magic fang", 1)], None),
    ("trident_e_uncharged", "Uncharged trident (e)", 59, 0.0,
     [("Uncharged trident (e)", 1), ("Magic fang", 1)], None),
    ("noxious_halberd", "Noxious halberd", 72, 100.0,
     [("Noxious point", 1), ("Noxious blade", 1), ("Noxious pommel", 1)], None),
    ("purging_staff", "Purging staff", 74, 730.0,
     [("Tormented synapse", 1), ("Iron bar", 1), ("Battlestaff", 1)],
     "730 XP on the first attach; 73 XP for each subsequent synapse."),
    ("bone_staff", "Bone staff", 35, 300.0,
     [("Battlestaff", 1), ("Chaos rune", 1000), ("Scurrius' spine", 1)], None),
    ("amulet_of_rancour", "Amulet of rancour", 86, 500.0,
     [("Amulet of torture", 1), ("Etched araxyte fang", 1)], None),
    ("necklace_of_rupture", "Necklace of rupture", 84, 500.0,
     [("Necklace of anguish", 1), ("Etched elder venator fang", 1)], None),
    ("accursed_sceptre", "Accursed sceptre", 85, 0.0,
     [("Thammaron's sceptre (u)", 1), ("Skull of Vet'ion", 1)], None),
    # --- crystal gear (tradeable seeds + shards) ---
    ("crystal_axe", "Crystal axe", 76, 6000.0,
     [("Dragon axe", 1), ("Crystal tool seed", 1), ("Crystal shard", 120)], None),
    ("crystal_pickaxe", "Crystal pickaxe", 76, 6000.0,
     [("Dragon pickaxe", 1), ("Crystal tool seed", 1), ("Crystal shard", 120)], None),
    ("crystal_harpoon", "Crystal harpoon", 76, 6000.0,
     [("Dragon harpoon", 1), ("Crystal tool seed", 1), ("Crystal shard", 120)], None),
    ("crystal_bow", "Crystal bow", 78, 2000.0,
     [("Crystal weapon seed", 1), ("Crystal shard", 40)], None),
    ("crystal_halberd", "Crystal halberd", 78, 2000.0,
     [("Crystal weapon seed", 1), ("Crystal shard", 40)], None),
    ("crystal_shield", "Crystal shield", 78, 2000.0,
     [("Crystal weapon seed", 1), ("Crystal shard", 40)], None),
    ("crystal_helm", "Crystal helm", 70, 2500.0,
     [("Crystal armour seed", 1), ("Crystal shard", 50)], None),
    ("crystal_legs", "Crystal legs", 72, 5000.0,
     [("Crystal armour seed", 2), ("Crystal shard", 100)], None),
    ("crystal_body", "Crystal body", 74, 7500.0,
     [("Crystal armour seed", 3), ("Crystal shard", 150)], None),
    ("blade_of_saeldor", "Blade of Saeldor", 82, 5000.0,
     [("Enhanced crystal weapon seed", 1), ("Crystal shard", 100)], None),
    ("bow_of_faerdhinen", "Bow of Faerdhinen", 82, 5000.0,
     [("Enhanced crystal weapon seed", 1), ("Crystal shard", 100)], None),
    ("enhanced_crystal_key", "Enhanced crystal key", 80, 500.0,
     [("Crystal key", 1), ("Crystal shard", 10)], None),
    ("eternal_teleport_crystal", "Eternal teleport crystal", 80, 5000.0,
     [("Enhanced crystal teleport seed", 1), ("Crystal shard", 100)], None),
]

# existing recipes to correct against the wiki XP table
PATCHES = {
    "sapphire_amulet": {"level": 1},  # stringing a (u) amulet is level 1, not the (u) level
}

SOURCE_NOTE_ADD = ("Crafting recipes expanded from the wiki Crafting/Experience table "
                   "(scripts/add_crafting.py): amulet/symbol stringing, pottery, glass, "
                   "misc tradeable crafts and boss/crystal combine crafts.")


def fetch_latest_ids() -> set[int]:
    req = urllib.request.Request(
        config.WIKI_BASE + "/latest", headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))["data"]
    return {int(k) for k, v in data.items()
            if v.get("high") is not None or v.get("low") is not None}


def main() -> int:
    dry = "--dry-run" in sys.argv
    mapping = itemdata.fetch_mapping()
    name_to_id, item_map = itemdata.index_mapping(mapping)
    lower_map = {m["name"].lower(): m["id"] for m in mapping}
    latest_ids = fetch_latest_ids()

    def resolve(name):
        if name in name_to_id:
            return name_to_id[name]
        return lower_map.get(name.lower())

    # names missing from /mapping (no GE price history): resolve via infoboxes
    all_names = [prod for _, prod, _, _, _, _ in C]
    all_names += [n for _, _, _, _, mats, _ in C for n, _ in mats]
    unresolved = sorted({n for n in all_names if resolve(n) is None})
    wiki_meta = itemdata.fetch_wiki_meta(unresolved) if unresolved else {}
    members_by_id = {int(m["id"]): bool(m.get("members")) for m in mapping}
    for n in unresolved:
        meta = wiki_meta.get(n)
        if meta and meta.get("id"):
            mid = int(meta["id"])
            name_to_id[n] = mid
            members_by_id[mid] = bool(meta.get("members"))

    existing = recipes_mod.load_recipes(config.RECIPES_DIR)
    existing_products = {r["product"]["item"].lower() for r in existing}
    existing_ids = {r["id"] for r in existing}

    new_recipes, problems, unpriced_rows = [], [], []
    for rid, prod, level, xp, mats, note in C:
        if rid in existing_ids or prod.lower() in existing_products:
            problems.append(f"SKIP dup: {rid} / {prod}")
            continue
        pid = resolve(prod)
        missing = []
        unpriced = []
        if pid is None:
            missing.append(prod)
        elif pid not in latest_ids:
            unpriced.append(prod)
        mats_out = []
        for name, qty in mats:
            mid = resolve(name)
            if mid is None:
                missing.append(name)
                continue
            if mid not in latest_ids:
                unpriced.append(name)
            mats_out.append({"item": name, "qty": qty})
        if missing:
            problems.append(f"SKIP unknown: {rid} -> {missing}")
            continue
        if unpriced:
            unpriced_rows.append(f"{rid} [{', '.join(unpriced)}]")
        members = members_by_id.get(pid, False) or any(
            members_by_id.get(resolve(n), False) for n, _ in mats)
        rec = {"id": rid, "skill": "crafting", "level": level, "xp": xp,
               "members": members,
               "product": {"item": prod, "qty": 1},
               "materials": mats_out, "fee": 0}
        if note:
            rec["note"] = note
        new_recipes.append(rec)

    # wiki corrections to already-present recipes
    patched = 0
    for r in existing:
        patch = PATCHES.get(r["id"])
        if patch:
            r.update(patch)
            patched += 1

    print(f"{len(new_recipes)} candidates pass, {len(problems)} skipped, {patched} patched:")
    for p in problems:
        print("  " + p)
    if unpriced_rows:
        print(f"\n{len(unpriced_rows)} recipes reference items with no GE price "
              "(partial cost, alchemy only):")
        for u in unpriced_rows:
            print("  ~ " + u)
    print("\nAdded:")
    for r in new_recipes:
        mats = ", ".join(f"{m['qty']}x {m['item']}" for m in r["materials"])
        print(f"  {r['level']:>3} {r['product']['item']:<38} {r['xp']:>6} xp  <- {mats}")

    if dry:
        print("\ndry run, not written")
        return 0

    # append to the crafting group (write_recipes keeps per-skill files grouped)
    meta = recipes_mod.load_meta(config.RECIPES_DIR)
    if SOURCE_NOTE_ADD not in meta.get("source", ""):
        meta["source"] = (meta.get("source", "")).rstrip() + " " + SOURCE_NOTE_ADD
    recipes_mod.write_recipes(config.RECIPES_DIR, existing + new_recipes, meta=meta)
    print(f"\nWrote {len(new_recipes)} recipes (+{patched} patched) to "
          f"{config.RECIPES_DIR}/crafting.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
