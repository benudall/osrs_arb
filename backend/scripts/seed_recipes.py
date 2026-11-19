"""Standalone: fetch mapping (if needed) and seed recipes into the DB.

Usage (from backend/):  python -m scripts.seed_recipes
"""
import sys

sys.path.insert(0, ".")

from app import config  # noqa: E402
from app.core import recipes as recipes_mod  # noqa: E402
from app.db import dao  # noqa: E402
from app.db.sqlite import Database  # noqa: E402
from app.providers.wiki_api import fetch_mapping_sync  # noqa: E402


def main() -> int:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = Database(config.DB_PATH)
    if not dao.get_name_to_id(db):
        print("items table empty; fetching /mapping ...")
        mapping = fetch_mapping_sync()
        dao.replace_items(db, mapping)
        print(f"stored {len(mapping)} items")
    report = recipes_mod.seed(db, config.RECIPES_PATH)
    print(report)
    return 0 if not report["unknown_items"] and not report["structural_errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
