import calendar
import json
import re
import time


# Suffix overrides for item images
# Format: {"Item Name": "suffix"}
#   "_5"      -> base name (trailing (n) stripped) + "_5"  e.g. "Bronze arrow" -> Bronze_arrow_5.png
#   "(3)"     -> base name (trailing (n) stripped) + "(3)" e.g. "Extended stamina potion(4)" -> Extended_stamina_potion(3).png
#   ""        -> strip trailing (n)  e.g. "Abyssal bracelet(5)" -> Abyssal_bracelet.png
#   "=Name"   -> use literal name as-is  e.g. "=Abyssal bracelet" -> Abyssal_bracelet.png (removes anything)
# Base-name keys also match variants with (n), e.g. "Extended stamina potion": "(3)" hits "Extended stamina potion(4)".
IMAGE_OVERRIDES = {
    "Abyssal bracelet(5)": "",
    "Adamant arrow": "_5",
    "Adamant bolts": "_5",
    "Adamant bolts(unf)": "_5",
    "Adamant brutal": "_5",
    "Adamant javelin tips": "_5",
    "Amethyst arrow": "_5",
    "Amethyst bolt tips": "_5",
    "Amethyst broad bolts": "_5",
    "Amethyst javelin tips": "_5",
    "Amylase crystal": "_5",
    "Ancient essence": "_500",
    "Arrow shaft": "_5",
    "Atlatl dart tips": "_5",
    "Atlatl dart": "_5",
    "Barbed bolts": "_5",
    "Broad bolts": "_5",
    "Bronze arrow": "_5",
    "Bronze bolts": "_5",
    "Bronze brutal": "_5",
    "Burning amulet(5)": "",
    "Castle wars bracelet(3)": "",
    "Diamond bolt tips": "_5",
    "Diamond bolts": "_5",
    "Dragon arrow": "_5",
    "Dragon bolts (unf)": "_5",
    "Dragon bolts": "_5",
    "Dragon javelin tips": "_5",
    "Dragonstone bolt tips": "_5",
    "Dragonstone bolts": "_5",
    "Emerald bolt tips": "_5",
    "Emerald bolts": "_5",
    "Extended stamina potion": "(3)",
    "Flighted ogre arrow": "_5",
    "Headless atlatl dart": "_5",
    "Iron arrow": "_5",
    "Iron bolts (unf)": "_5",
    "Iron bolts": "_5",
    "Iron brutal": "_5",
    "Jade bolt tips": "_5",
    "Javelin shaft": "_5",
    "Lava scale shard": "_5",
    "Mithril arrow": "_5",
    "Mithril bolts (unf)": "_5",
    "Mithril bolts": "_5",
    "Mithril brutal": "_5",
    "Moonlight antler bolts": "_5",
    "Ogre arrow shaft": "_5",
    "Onyx bolt tips": "_5",
    "Onyx bolts": "_5",
    "Opal bolt tips": "_5",
    "Opal bolts": "_5",
    "Opal dragon bolts": "_5",
    "Ruby bolt tips": "_5",
    "Ruby bolts": "_5",
    "Rune arrow": "_5",
    "Rune brutal": "_5",
    "Rune javelin tips": "_5",
    "Runite bolts (unf)": "_5",
    "Runite bolts": "_5",
    "Sapphire bolt tips": "_5",
    "Sapphire bolts": "_5",
    "Steel arrow": "_5",
    "Steel bolts (unf)": "_5",
    "Steel bolts": "_5",
    "Steel brutal": "_5",
    "Steel javelin tips": "_5",
    "Sunlight antler bolts": "_5",
    "Topaz bolt tips": "_5",
    "Topaz bolts": "_5",
    "Unfinished broad bolts": "_5",
    "Zulrah's scales": "_5",
}


def replace_items(db, mapping):
    """mapping: list of {id, name, members, limit, highalch, value, ...} from /mapping.

    Atomic: readers never see an empty/partial items table mid-replace."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows = [
        (
            int(m["id"]),
            m["name"],
            1 if m.get("members") else 0,
            m.get("limit"),
            m.get("highalch"),
            m.get("value"),
            _get_item_image_url(m["name"]),
            now,
        )
        for m in mapping
    ]
    with db.transaction() as conn:
        conn.execute("DELETE FROM items")
        conn.executemany(
            "INSERT INTO items (id, name, members, buy_limit, highalch, value, image_url, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )


def _get_item_image_url(name: str) -> str:
    """Generates the wiki image URL for an item, handling overrides and special cases."""
    def _url(image_name: str) -> str:
        return f"https://oldschool.runescape.wiki/images/{image_name.replace(' ', '_')}.png"

    suffix = IMAGE_OVERRIDES.get(name)
    if suffix is None:
        base_name = re.sub(r'\(\d+\)$', '', name)
        suffix = IMAGE_OVERRIDES.get(base_name)

    if suffix is None:
        # No override: use raw name
        return _url(name)

    if suffix.startswith("="):
        # Full literal replacement: "=Some name" -> Some_name.png
        return _url(suffix[1:])

    # Suffix mode: strip trailing (n) from name, then append suffix
    clean_name = re.sub(r'\(\d+\)$', '', name)
    return _url(clean_name + suffix)


def items_stale(db, ttl_secs):
    row = db.query_one("SELECT MAX(updated_at) AS u FROM items")
    if not row or not row["u"]:
        return True
    try:
        # stored UTC: parse with timegm (mktime would apply the local offset)
        last = calendar.timegm(time.strptime(row["u"], "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return True
    return (time.time() - last) > ttl_secs


def get_item_map(db):
    return {
        r["id"]: {
            "id": r["id"],
            "name": r["name"],
            "members": bool(r["members"]),
            "buy_limit": r["buy_limit"],
            "value": r["value"],
            "image_url": r["image_url"],
        }
        for r in db.query("SELECT id, name, members, buy_limit, value, image_url FROM items")
    }


def get_name_to_id(db):
    return {r["name"]: r["id"] for r in db.query("SELECT id, name FROM items")}


def insert_snapshots(db, rows):
    """rows: (item_id, ts, high, low, high_vol, low_vol, source)"""
    if rows:
        db.executemany(
            "INSERT OR REPLACE INTO price_snapshots (item_id, ts, high, low, high_vol, low_vol, source) "
            "VALUES (?,?,?,?,?,?,?)",
            rows,
        )


def prune_snapshots(db, ttl_secs):
    """Delete price_snapshots older than ttl_secs (bounds table growth)."""
    cutoff = int(time.time()) - ttl_secs
    db.execute("DELETE FROM price_snapshots WHERE ts < ?", (cutoff,))


def get_recipes(db):
    rows = db.query("SELECT * FROM recipes ORDER BY skill, level, id")
    for r in rows:
        r["members"] = bool(r["members"])
        r.setdefault("xp", 0)
        r["product"] = {"item_id": r.pop("product_item_id"), "qty": r.pop("product_qty")}
        r["materials"] = json.loads(r.pop("materials_json"))
        r["tools"] = json.loads(r.pop("tools_json") or "[]")
        r["facilities"] = json.loads(r.pop("facilities_json") or "[]")
        r["extra_skills"] = json.loads(r.pop("extra_skills_json") or "[]")
    return rows


def replace_recipes(db, recipes):
    """recipes: resolved dicts with product_item_id, materials [{item_id, qty}], fee, note.

    Atomic: readers never see an empty/partial recipes table mid-replace."""
    rows = [
        (
            r["id"], r["skill"], r["level"], r.get("xp", 0), 1 if r["members"] else 0,
            r["product"]["item_id"], r["product"]["qty"],
            json.dumps(r["materials"]), r.get("fee", 0), r.get("note"),
            json.dumps(r.get("tools") or []), json.dumps(r.get("facilities") or []),
            json.dumps(r.get("extra_skills") or []),
        )
        for r in recipes
    ]
    with db.transaction() as conn:
        conn.execute("DELETE FROM recipes")
        conn.executemany(
            "INSERT INTO recipes (id, skill, level, xp, members, product_item_id, product_qty, materials_json, fee, note, tools_json, facilities_json, extra_skills_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )


def get_player(db, name):
    return db.query_one("SELECT * FROM players WHERE name = ?", (name,))


def upsert_player(db, name, skills_json):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    db.execute(
        "INSERT INTO players (name, skills_json, fetched_at) VALUES (?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET skills_json = excluded.skills_json, fetched_at = excluded.fetched_at",
        (name, skills_json, now),
    )


def distinct_skills(db):
    return [r["skill"] for r in db.query("SELECT DISTINCT skill FROM recipes ORDER BY skill")]
