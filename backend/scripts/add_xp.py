"""Add an 'xp' field to every recipe in data/recipes/<skill>.json.

Source: OSRS wiki '<Skill>/Experience table' pages (the canonical per-recipe
experience lists). Each wiki row is matched to a recipe by product name
(variant suffixes like '(Normal furnace)' are stripped) with the recipe level
as a tie-breaker when the same item has multiple XP values.

Usage (from backend/):  python scripts/add_xp.py [--dry-run]

Without --dry-run the file is rewritten (xp inserted right after 'level');
with --dry-run only the match report is printed.
"""
import json
import re
import sys

sys.path.insert(0, ".")
import config  # noqa: E402
import recipes as recipes_mod  # noqa: E402
from scripts.harvest_recipes import TableCollector, cell_text, fetch  # noqa: E402

# skill -> (page, None) or (page, table_index) when the page has several
# experience tables and we want one specifically
SOURCES = {
    "smithing": ("Smithing/Experience table", 0),
    "cooking": ("Cooking/Experience table", 0),
    "crafting": ("Crafting/Experience table", 0),
    "fletching": ("Fletching/Experience table", 0),
    "herblore": ("Herblore/Experience table", 0),
    "magic": ("Magic/Experience table", 4),  # "Other experience sources"
}


def norm(s: str) -> str:
    s = s.replace("\u2019", "'").lower()
    return re.sub(r"\s+", " ", s).strip()


def base_name(s: str) -> str:
    """'Bronze bar (Normal furnace)' -> 'bronze bar' (strip trailing variant)."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", s)


def extract_rows(page: str, table_index: int):
    html = fetch(page)
    parser = TableCollector()
    parser.feed(html)
    parser.close()
    t = parser.tables[table_index]
    hdrs = [cell_text(h) if h is not None else "" for h in t["headers"]]
    low = [h.lower() for h in hdrs]
    xp_i = next((i for i, h in enumerate(low) if re.search(r"\bxp\b", h)), None)
    lvl_i = next((i for i, h in enumerate(low) if "level" in h), None)
    mat_i = next((i for i, h in enumerate(low) if "material" in h), None)
    if xp_i is None:
        raise RuntimeError(f"{page}: no XP column in headers {hdrs}")
    rows = []
    for r in t["rows"]:
        if 0 >= len(r) or r[0] is None:
            continue
        name = cell_text(r[0])
        if not name:
            continue
        lvl = None
        if lvl_i is not None and lvl_i < len(r):
            m = re.search(r"(\d+)", cell_text(r[lvl_i]))
            if m:
                lvl = int(m.group(1))
        m = re.search(r"(\d+(?:\.\d+)?)", cell_text(r[xp_i]))
        if not m:
            continue
        xp = float(m.group(1))
        mats = norm(cell_text(r[mat_i])) if mat_i is not None and mat_i < len(r) else ""
        rows.append({"name": name, "base": norm(base_name(name)), "lvl": lvl,
                     "xp": xp, "mats": mats})
    return rows


def dose_of(name: str):
    m = re.search(r"\((\d+)\)\s*$", name)
    return int(m.group(1)) if m else None


def mat_units(mats: str) -> int:
    return sum(int(q) for q in re.findall(r"(\d+)\s*\u00d7", mats))


def match_recipe(recipe: dict, rows: list):
    """Score wiki rows against the recipe; return (xp, status, detail).

    status: ok | weak | no-match. 'weak' = matched, but worth a human look.
    """
    prod = norm(recipe["product"]["item"])
    prod_base = base_name(prod)
    prod_dose = dose_of(prod)
    recipe_mats = [norm(m["item"]) for m in recipe["materials"]]

    best, best_score = None, -10**9
    for r in rows:
        rname, rbase = norm(r["name"]), r["base"]
        # name relationship
        if rname == prod:
            name_score = 100
        elif prod.startswith(rname + " ") or prod.startswith(rname + "("):
            # candidate 'Antidote+' vs recipe 'Antidote+(3)'
            name_score = 80
        elif rname.startswith(prod_base) and rname != prod_base:
            # candidate 'Antidote+ (unf)' vs recipe 'Antidote+(3)'
            name_score = 40
        elif rbase == prod_base:
            name_score = 20
        else:
            continue
        score = name_score
        # level
        score += 10 if r["lvl"] == recipe["level"] else -10
        # materials overlap
        for m in recipe_mats:
            if m in r["mats"]:
                score += 8
        # dose match (recipe 'Antifire potion(3)' inside candidate materials)
        rdose = None
        dm = re.findall(r"\((\d+)\)", r["mats"])
        if dm:
            rdose = max(int(x) for x in dm)
        if prod_dose is not None and rdose is not None:
            score += 15 if rdose == prod_dose else -15
        # bonus-variant penalties
        if "catalyst" in r["mats"]:
            score -= 3
        if re.search(r"\brune\b", r["mats"]):
            score -= 3
        # prefer fewer material units on ties
        score -= mat_units(r["mats"]) * 0.01
        if score > best_score:
            best, best_score = r, score

    if best is None:
        return None, "no-match", ""
    detail = f"wiki_name={best['name']} lvl={best['lvl']} xp={best['xp']} score={best_score:.1f}"
    # sanity: exact name or strong prefix, and level close
    weak = best_score < 100
    return best["xp"], ("weak" if weak else "ok"), detail


def main():
    dry = "--dry-run" in sys.argv
    recipes = recipes_mod.load_recipes(config.RECIPES_DIR)

    wiki = {}
    for skill, (page, ti) in SOURCES.items():
        rows = extract_rows(page, ti)
        wiki[skill] = rows
        print(f"{skill}: {len(rows)} wiki rows from {page}")
    by_base = {s: {} for s in wiki}
    for s, rows in wiki.items():
        for r in rows:
            by_base[s].setdefault(r["base"], []).append(r)

    # Tanning / soda-ash actions are tannery or range services in OSRS: no XP.
    manual = {
        ("crafting", "leather"): 0,
        ("crafting", "hard leather"): 0,
        ("crafting", "soda ash"): 0,
        ("crafting", "green dragon leather"): 0,
        ("crafting", "blue dragon leather"): 0,
    }

    report = {"ok": 0, "weak": [], "no-match": []}
    new_recipes = []
    for r in recipes:
        key = (r["skill"], norm(r["product"]["item"]))
        if key in manual:
            xp, status, detail = manual[key], "manual", "tannery/range service (wiki)"
        else:
            xp, status, detail = match_recipe(r, wiki[r["skill"]])
        if status in ("ok", "manual"):
            report["ok"] += 1
        elif status == "no-match":
            report["no-match"].append((r["skill"], r["id"], r["product"]["item"], r["level"], detail))
            xp = None
        else:
            report["weak"].append((r["skill"], r["id"], r["product"]["item"], r["level"], detail))
        nr = {}
        for k, v in r.items():
            nr[k] = v
            if k == "level" and xp is not None:
                nr["xp"] = xp
        if "xp" not in nr and xp is not None:
            nr["xp"] = xp
        new_recipes.append(nr)

    print(f"\nok/manual: {report['ok']}/{len(recipes)}")
    print(f"weak (review): {len(report['weak'])}")
    for a in report["weak"]:
        print("  W", *a)
    print(f"no-match: {len(report['no-match'])}")
    for a in report["no-match"]:
        print("  N", *a)

    if not dry:
        recipes_mod.write_recipes(config.RECIPES_DIR, new_recipes)
        print(f"\nwritten: {config.RECIPES_DIR}/")


if __name__ == "__main__":
    main()
