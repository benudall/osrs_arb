"""Generate parity fixtures for the JS profit/pricestore ports.

One-time (re-run when the math or the baked data changes): pulls live prices,
freezes the clock, evaluates every recipe with the PYTHON reference
implementation, and stores inputs + expected outputs in tests/fixtures.json.
backend/scripts/parity_check.cjs then replays the same inputs through the JS
port (profit.js + pricestore.js) and diffs the results.

The wiki payloads are trimmed to items actually referenced by the baked data,
so the committed fixture stays small.

Usage (from backend/):  python scripts/gen_fixtures.py
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, ".")

import config  # noqa: E402
import profit  # noqa: E402
from pricestore import PriceStore  # noqa: E402


def fetch_wiki(path: str) -> dict:
    req = urllib.request.Request(
        config.WIKI_BASE + path, headers={"User-Agent": config.USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def to_resolved(baked: dict) -> dict:
    """Baked recipe shape ({product: {id, qty}}) -> profit.py shape ({item_id})."""
    return {
        "id": baked["id"],
        "skill": baked["skill"],
        "level": baked["level"],
        "extra_skills": baked.get("extra_skills") or [],
        "xp": baked["xp"],
        "members": baked["members"],
        "product": {"item_id": baked["product"]["id"], "qty": baked["product"]["qty"]},
        "materials": [{"item_id": m["id"], "qty": m["qty"]} for m in baked["materials"]],
        "fee": baked.get("fee", 0),
        "note": baked.get("note"),
        "tools": [{"item_id": t["id"], "name": t["name"]} for t in baked.get("tools") or []],
        "facilities": baked.get("facilities") or [],
    }


def main() -> int:
    items_doc = json.loads(config.SITE_ITEMS_PATH.read_text(encoding="utf-8"))
    recipes = []
    for path in sorted(config.SITE_RECIPES_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        recipes.extend(json.loads(path.read_text(encoding="utf-8")))
    item_ids = set(items_doc["items"].keys())
    item_map = {
        int(iid): {
            "id": int(iid),
            "name": v["name"],
            "members": v["members"],
            "buy_limit": v["limit"],
            "value": v["value"],
            "image_url": v["image"],
        }
        for iid, v in items_doc["items"].items()
    }
    resolved = [to_resolved(r) for r in recipes]

    now = int(time.time())
    latest = fetch_wiki("/latest")
    w5 = fetch_wiki("/5m")
    w1 = fetch_wiki("/1h")

    # trim payloads to referenced items (keeps fixtures small; resolution for
    # unreferenced items is irrelevant to recipe evaluation)
    def trim(data: dict) -> dict:
        return {k: v for k, v in data.items() if k in item_ids}

    wiki = {"latest": trim(latest.get("data", {})),
            "5m": trim(w5.get("data", {})),
            "1h": trim(w1.get("data", {}))}

    store = PriceStore(stale_secs=config.STALE_SECS, now_fn=lambda: now)
    store.update_latest({"data": wiki["latest"]})
    store.update_window({"data": wiki["5m"]}, "5m")
    store.update_window({"data": wiki["1h"]}, "1h")

    expected = {}
    for mode in ("conservative", "optimistic"):
        rows, _ = profit.evaluate_all(resolved, item_map, store, mode=mode)
        expected[mode] = rows

    # store-resolution outputs for every referenced item (guards pricestore.js)
    resolve_samples = {iid: store.resolve(int(iid)) for iid in sorted(item_ids, key=int)}

    fixtures = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "now": now,
        "stale_secs": config.STALE_SECS,
        "wiki": wiki,
        "items": items_doc["items"],
        "recipes": recipes,
        "resolve_samples": resolve_samples,
        "expected": expected,
    }
    config.FIXTURES_PATH.write_text(
        json.dumps(fixtures, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    n_rows = sum(len(v) for v in expected.values())
    print(f"fixtures: {len(resolved)} recipes x 2 modes = {n_rows} expected rows, "
          f"{len(resolve_samples)} resolve samples -> {config.FIXTURES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
