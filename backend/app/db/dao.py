import json
import time


def replace_items(db, mapping):
    """mapping: list of {id, name, members, limit, highalch, value, ...} from /mapping."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    db.execute("DELETE FROM items")
    db.executemany(
        "INSERT INTO items (id, name, members, buy_limit, highalch, value, updated_at) VALUES (?,?,?,?,?,?,?)",
        [
            (int(m["id"]), m["name"], 1 if m.get("members") else 0, m.get("limit"), m.get("highalch"), m.get("value"), now)
            for m in mapping
        ],
    )


def items_stale(db, ttl_secs):
    row = db.query_one("SELECT MAX(updated_at) AS u FROM items")
    if not row or not row["u"]:
        return True
    try:
        last = time.mktime(time.strptime(row["u"], "%Y-%m-%dT%H:%M:%SZ"))
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
        }
        for r in db.query("SELECT id, name, members, buy_limit, value FROM items")
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


def get_recipes(db):
    rows = db.query("SELECT * FROM recipes ORDER BY skill, level, id")
    for r in rows:
        r["members"] = bool(r["members"])
        r.setdefault("xp", 0)
        r["product"] = {"item_id": r.pop("product_item_id"), "qty": r.pop("product_qty")}
        r["materials"] = json.loads(r.pop("materials_json"))
        r["tools"] = json.loads(r.pop("tools_json") or "[]")
        r["facilities"] = json.loads(r.pop("facilities_json") or "[]")
    return rows


def replace_recipes(db, recipes):
    """recipes: resolved dicts with product_item_id, materials [{item_id, qty}], fee, note."""
    db.execute("DELETE FROM recipes")
    db.executemany(
        "INSERT INTO recipes (id, skill, level, xp, members, product_item_id, product_qty, materials_json, fee, note, tools_json, facilities_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                r["id"], r["skill"], r["level"], r.get("xp", 0), 1 if r["members"] else 0,
                r["product"]["item_id"], r["product"]["qty"],
                json.dumps(r["materials"]), r.get("fee", 0), r.get("note"),
                json.dumps(r.get("tools") or []), json.dumps(r.get("facilities") or []),
            )
            for r in recipes
        ],
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
