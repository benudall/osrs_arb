"""Harvest recipes from OSRS wiki skill guide pages into data/harvested_raw.json.

Parses the rendered HTML tables (action=parse&prop=text), handling rowspans,
colspans, nested tables, plink double-links, and qty patterns like "x3" / "2 x".
Output is reviewed/merged by scripts/merge_harvested.py - nothing here touches
the DB.

Usage (from backend/):  python scripts/harvest_recipes.py
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

sys.path.insert(0, ".")
import config  # noqa: E402

OUT_PATH = config.HARVESTED_PATH

UA = "osrs_arb recipe harvester (contact: dev)"

PAGES = [
    ("Smithing", "smithing"),
    ("Cooking", "cooking"),
    ("Crafting", "crafting"),
    ("Fletching", "fletching"),
    ("Herblore", "herblore"),
    ("Lvl-1 Enchant", "magic"),
    ("Lvl-2 Enchant", "magic"),
    ("Lvl-3 Enchant", "magic"),
    ("Lvl-4 Enchant", "magic"),
    ("Lvl-5 Enchant", "magic"),
    ("Lvl-6 Enchant", "magic"),
    ("Lvl-7 Enchant", "magic"),
]

ENCHANT_LEVELS = {"Lvl-1 Enchant": 7, "Lvl-2 Enchant": 27, "Lvl-3 Enchant": 49,
                  "Lvl-4 Enchant": 57, "Lvl-5 Enchant": 68, "Lvl-6 Enchant": 87,
                  "Lvl-7 Enchant": 93}

SECTION_BAR_MAP = {"bronze": "Bronze bar", "iron": "Iron bar", "steel": "Steel bar",
                   "mithril": "Mithril bar", "adamantite": "Adamantite bar",
                   "adamant": "Adamantite bar", "runite": "Runite bar",
                   "rune": "Runite bar", "gold": "Gold bar", "silver": "Silver bar"}

# tools present in materials cells but never consumed
TOOL_RE = re.compile(
    r"\b(mould|mold|hammer|needle|knife|chisel|glassblowing pipe|pestle and mortar|"
    r"spinning wheel|tinderbox|shears|sickle?\s*mould|swamp paste)\b", re.I)


def fetch(page):
    url = "https://oldschool.runescape.wiki/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": page, "prop": "text", "format": "json",
         "formatversion": "2", "redirects": "1"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["parse"]["text"]


def link_name(href):
    name = urllib.parse.unquote(href.split("#")[0])
    name = name.replace("_", " ").strip()
    if name.startswith("/w/"):
        name = name[3:]
    name = name.replace("\u2019", "'")  # curly apostrophes from HTML
    if not name or name.startswith(("File:", "Special:")):
        return None
    return name


class TableCollector(HTMLParser):
    """Collects (headings, headers, rows) for every top-level table.

    Cell = {"text": str with \x00 <name> \x00 markers at link positions,
            "names": [item names in order]}
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []       # finished tables
        self.stack = []        # open table contexts
        self.heading_stack = []  # current (tag, text-buffer) for h1-h6
        self.headings = []     # flat list of heading texts seen so far
        self._heading_buf = None
        self._cell = None      # (buf_list, names) for innermost open cell

    # -- helpers ---------------------------------------------------------
    def _ctx(self):
        return self.stack[-1] if self.stack else None

    def _buf_add(self, s):
        if self._cell is not None:
            self._cell[0].append(s)
        elif self._heading_buf is not None:
            self._heading_buf.append(s)

    # -- tag handlers ----------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading_buf = []
        elif tag == "table":
            self.stack.append({
                "headings": list(self.headings), "headers": [], "rows": [],
                "row": None, "row_is_head": False,
                "pending": {},  # col -> [rows_left, cellcopy]
                "max_cols": 0,
            })
            self._cell = None
        elif tag == "tr":
            ctx = self._ctx()
            if ctx is not None:
                ctx["row"] = []
                ctx["row_is_head"] = False
        elif tag in ("td", "th"):
            ctx = self._ctx()
            if ctx is not None and ctx["row"] is not None:
                if tag == "th":
                    ctx["row_is_head"] = True
                self._cell = [[], []]
                ctx["_span"] = int(a.get("colspan", 1) or 1)
                ctx["_rowspan"] = int(a.get("rowspan", 1) or 1)
            else:
                self._cell = None
        elif tag == "a":
            ctx = self._ctx()
            href = a.get("href", "")
            if ctx is not None and self._cell is not None and href.startswith("/w/"):
                name = link_name(href)
                if name:
                    self._cell[0].append(f"\x00{name}\x00")
                    self._cell[1].append(name)

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if self._heading_buf is not None:
                text = re.sub(r"\s+", " ", "".join(self._heading_buf)).strip()
                if text:
                    self.headings.append(text)
                self._heading_buf = None
        elif tag in ("td", "th"):
            ctx = self._ctx()
            if ctx is not None and self._cell is not None:
                cell = {"text": "".join(self._cell[0]), "names": self._cell[1]}
                span = ctx.pop("_span", 1)
                rowspan = ctx.pop("_rowspan", 1)
                col = len(ctx["row"])
                ctx["row"].append(cell)
                for _ in range(span - 1):
                    ctx["row"].append(None)  # placeholder for colspan
                if rowspan > 1:
                    ctx["pending"][col] = [rowspan - 1, cell]
                self._cell = None
        elif tag == "tr":
            ctx = self._ctx()
            if ctx is not None and ctx["row"] is not None:
                # fill from pending rowspans
                filled = []
                for i in range(max(ctx["max_cols"], len(ctx["row"]))):
                    if i < len(ctx["row"]) and ctx["row"][i] is not None:
                        filled.append(ctx["row"][i])
                    elif i in ctx["pending"]:
                        filled.append(ctx["pending"][i][1])
                    else:
                        filled.append(None)
                for col, (left, _) in list(ctx["pending"].items()):
                    if left - 1 <= 0:
                        del ctx["pending"][col]
                    else:
                        ctx["pending"][col][0] = left - 1
                ctx["max_cols"] = max(ctx["max_cols"], len(filled))
                if ctx["row_is_head"]:
                    if not ctx["headers"]:
                        ctx["headers"] = filled
                    else:
                        # multi-row header: fill None slots from continuation rows
                        for i in range(len(filled)):
                            if i < len(ctx["headers"]) and ctx["headers"][i] is None and filled[i] is not None:
                                ctx["headers"][i] = filled[i]
                            elif i >= len(ctx["headers"]):
                                ctx["headers"].append(filled[i])  # keep None colspan placeholders for column alignment
                elif any(c is not None and (c["names"] or c["text"].strip()) for c in filled):
                    ctx["rows"].append(filled)
                ctx["row"] = None
        elif tag == "table":
            ctx = self.stack.pop()
            if ctx["headers"]:
                self.tables.append(ctx)
            # restore outer cell buffer
            self._cell = None

    def handle_data(self, data):
        if data:
            self._buf_add(data)


def cell_names(cell):
    """Deduped item names in order (plink renders icon+text links twice)."""
    out = []
    for n in cell["names"]:
        if n not in out or (out and out[-1] != n):
            if not out or out[-1] != n:
                out.append(n)
    return out


def seg_qty(text):
    """Qty pattern in a text segment: 'x3', '3 x', 'x 15' -> int or None."""
    m = re.search(r"(\d+)\s*[x\u00d7]\s*(?:$|[\s\x00])", text)
    if m:
        return int(m.group(1))
    m = re.search(r"[x\u00d7]\s*(\d+)", text)
    if m:
        return int(m.group(1))
    return None


def parse_materials(cell):
    """Material cell -> [{item, qty}] using \x00 markers as link boundaries."""
    parts = re.split(r"\x00([^\x00]+)\x00", cell["text"])
    # parts: [pre, name, mid, name, post, ...]
    mats, seen = [], set()
    for i in range(1, len(parts), 2):
        name = parts[i]
        if name in seen:
            continue
        seen.add(name)
        after = parts[i + 1] if i + 1 < len(parts) else ""
        before = parts[i - 1]
        qty = seg_qty(after[:15]) or seg_qty(before[-15:])
        qty = qty or 1
        if TOOL_RE.search(name):
            continue
        mats.append({"item": name, "qty": qty})
    return mats


def cell_tool_names(cell):
    """Tool names present in a materials cell (they are never consumed)."""
    return [n for n in cell_names(cell) if TOOL_RE.search(n)]


def parse_product(cell):
    names = cell_names(cell)
    if not names:
        return None
    qty = seg_qty(cell["text"]) or 1
    return {"item": names[0], "qty": qty}


def parse_level(cell):
    if cell is None:
        return None
    m = re.search(r"\d+", cell["text"])
    return int(m.group(0)) if m else None


def cell_text(cell):
    return re.sub(r"\s+", " ", re.sub(r"\x00", " ", cell["text"])).strip() if cell else ""


def header_index(headers, names):
    for i, h in enumerate(headers):
        if h is None:
            continue
        if any(n.lower() in cell_text(h).lower() for n in names):
            return i
    return None


# ---------------------------------------------------------------------------
# table rules: each = dict(required_headers, product_col, level_col,
#                          material_cols, counted_cols, section_map, skip_sections)
# ---------------------------------------------------------------------------

def rules_for(page):
    if page == "Smithing":
        return [
            {  # smelting
                "req": ["Level", "Bar", "Ore"],
                "product": "Bar", "level": "Level",
                "material_cols": ["Ore"], "members_col": "Members",
            },
            {  # bar forging per metal section (Level, Item, XP, Bars, ...)
                "req": ["Level", "Item", "Bars"],
                "product": "Item", "level": "Level",
                "counted": [("Bars", "section_bar")], "members_col": "Members",
                "skip_sections": ["blast furnace", "gold", "silver", "other"],
            },
            {  # gold helmets etc (Level, Item, XP, Bars, Members)
                "req": ["Level", "Item", "Experience", "Bars", "Members"],
                "product": "Item", "level": "Level",
                "counted": [("Bars", "section_bar")], "members_col": "Members",
            },
            {  # dragon sq shield / signets
                "req": ["Item", "Skills", "Materials"],
                "product": "Item", "material_cols": ["Materials"],
            },
        ]
    if page == "Cooking":
        return [{"req": ["Level", "Item", "Healing", "Members"],
                 "product": "Item", "level": "Level", "members_col": "Members",
                 "raw_infer": True}]
    if page in ("Crafting", "Fletching", "Herblore"):
        product_names = ["Item", "Unstrung bows", "Bows", "Arrow", "Arrows", "Bolts",
                         "Dragon bolts", "Dart", "Javelin", "Shield", "Blowpipe"]
        out = [
            {"req": ["Level", "Materials"], "product": product_names, "level": "Level",
             "material_cols": ["Materials"]},
        ]
        if page == "Herblore":
            out = [
                {  # herb cleaning + unfinished potions
                    "req": ["Grimy Herb", "Clean Herb", "Unfinished potion"],
                    "special": "herblore_herbs",
                },
                {  # potions: base + primary + secondary
                    "req": ["Level", "Potion", "Potion Base", "Secondary Ingredient"],
                    "product": "Potion", "level": "Level",
                    "material_cols": ["Potion Base", "Primary Ingredient", "Secondary Ingredient"],
                },
                {  # tars etc
                    "req": ["Level", "Product", "Primary Ingredient", "Secondary Ingredient"],
                    "product": "Product", "level": "Level",
                    "material_cols": ["Primary Ingredient", "Secondary Ingredient"],
                },
            ]
        return out
    if page.startswith("Lvl-"):
        return [
            {"pair": [["Unenchanted", "Enchanted"], ["Item", "Item"]],
             "fixed_materials": [{"item": "Cosmic rune", "qty": 1}],
             "fixed_level": ENCHANT_LEVELS[page]},
        ]
    return []


SECTION_BAR_HINTS = ["bronze", "iron", "steel", "mithril", "adamantite", "runite", "adamant", "rune", "gold", "silver"]


def harvest_page(page_title, skill, parser):
    html = fetch(page_title)
    parser.tables = []   # reset per page - never match tables harvested from other pages
    parser.stack = []
    parser.headings = []
    parser.feed(html)
    parser.close()
    out = []
    for t in parser.tables:
        hdr_texts = [cell_text(h).lower() if h is not None else "" for h in t["headers"]]
        for rule in rules_for(page_title):
            if "pair" not in rule and not all(any(req.lower() in h for h in hdr_texts) for req in rule["req"]):
                continue
            section = (t["headings"][-1] if t["headings"] else "").lower()
            if any(s in section for s in rule.get("skip_sections", [])):
                continue
            out.extend(apply_rule(t, rule, section, skill, page_title))
    return out


def apply_rule(t, rule, section, skill, page_title):
    if rule.get("special") == "herblore_herbs":
        rows_out = []
        g_i = header_index(t["headers"], ["Grimy Herb"])
        c_i = header_index(t["headers"], ["Clean Herb"])
        u_i = header_index(t["headers"], ["Unfinished potion"])
        lg_i = header_index(t["headers"], ["Level (cleaning)", "Level(cleaning)"])
        lu_i = header_index(t["headers"], ["Level (unf", "Level(unf"])
        for row in t["rows"]:
            g = row[g_i] if g_i is not None and g_i < len(row) else None
            c = row[c_i] if c_i is not None and c_i < len(row) else None
            u = row[u_i] if u_i is not None and u_i < len(row) else None
            clean = parse_product(c)
            if clean:
                rows_out.append({
                    "skill": skill, "level": parse_level(row[lg_i]) if lg_i is not None else None,
                    "product": clean, "materials": [parse_materials(g)[0]] if g else [],
                    "source": page_title, "section": section,
                })
            unf = parse_product(u)
            if unf and clean:
                rows_out.append({
                    "skill": skill, "level": parse_level(row[lu_i]) if lu_i is not None else None,
                    "product": unf,
                    "materials": [{"item": clean["item"], "qty": 1}, {"item": "Vial of water", "qty": 1}],
                    "source": page_title, "section": section,
                })
        return rows_out

    rows_out = []
    if rule.get("special") == "herblore_herbs":
        g_i = header_index(t["headers"], ["Grimy Herb"])
        c_i = header_index(t["headers"], ["Clean Herb"])
        u_i = header_index(t["headers"], ["Unfinished potion"])
        lg_i = header_index(t["headers"], ["Level (cleaning)", "Level(cleaning)"])
        lu_i = header_index(t["headers"], ["Level (unf", "Level(unf"])
        for row in t["rows"]:
            g = row[g_i] if g_i is not None and g_i < len(row) else None
            c = row[c_i] if c_i is not None and c_i < len(row) else None
            u = row[u_i] if u_i is not None and u_i < len(row) else None
            clean = parse_product(c)
            if clean:
                rows_out.append({
                    "skill": skill, "level": parse_level(row[lg_i]) if lg_i is not None else None,
                    "product": clean, "materials": [parse_materials(g)[0]] if g else [],
                    "source": page_title, "section": section,
                })
            unf = parse_product(u)
            if unf and clean:
                rows_out.append({
                    "skill": skill, "level": parse_level(row[lu_i]) if lu_i is not None else None,
                    "product": unf,
                    "materials": [{"item": clean["item"], "qty": 1}, {"item": "Vial of water", "qty": 1}],
                    "source": page_title, "section": section,
                })
        return rows_out

    if rule.get("pair"):
        headers = [cell_text(h) for h in t["headers"]]
        low = [h.lower() if h is not None else "" for h in headers]
        prod_i = mat_i = None
        for mat_name, prod_name in rule["pair"]:
            m_idx = [i for i, h in enumerate(low) if mat_name.lower() in h]
            p_idx = [i for i, h in enumerate(low) if prod_name.lower() in h and i > (m_idx[0] if m_idx else -1)]
            if m_idx and p_idx:
                mat_i, prod_i = m_idx[0], p_idx[0]
                break
        if prod_i is None:
            return []
        lvl_i = None
        mat_cols = [mat_i]
    else:
        prod_names = rule["product"] if isinstance(rule["product"], list) else [rule["product"]]
        prod_i = header_index(t["headers"], prod_names)
        lvl_i = header_index(t["headers"], [rule.get("level", "Level")])
        mat_cols = [header_index(t["headers"], [c]) for c in rule.get("material_cols", [])]
    members_i = header_index(t["headers"], ["members"]) if rule.get("members_col") else None

    if prod_i is None:
        return []
    fixed_mats = rule.get("fixed_materials", [])
    for row in t["rows"]:
        if prod_i >= len(row):
            continue
        product = parse_product(row[prod_i])
        if not product or product["item"].lower() in ("grand exchange", "coins"):
            continue
        level = rule.get("fixed_level")
        if level is None and lvl_i is not None and lvl_i < len(row):
            level = parse_level(row[lvl_i])
        if level is None or level > 99:
            continue
        materials = list(fixed_mats)
        seen_mats = {m["item"] for m in materials}
        tools = []
        for ci in mat_cols:
            if ci is not None and ci < len(row) and row[ci]:
                tools.extend(n for n in cell_tool_names(row[ci]) if n not in tools)
                for m in parse_materials(row[ci]):
                    if m["item"] not in seen_mats:  # plink/icon dupes across cols: keep first
                        seen_mats.add(m["item"])
                        materials.append(m)
        for col_name, kind in rule.get("counted", []):
            ci = header_index(t["headers"], [col_name])
            if ci is not None and ci < len(row) and row[ci]:
                qty = parse_level(row[ci])
                if qty:
                    if kind == "section_bar":
                        bar = next((SECTION_BAR_MAP[m] for m in SECTION_BAR_HINTS if m in section), None)
                        if not bar:
                            continue
                        materials.append({"item": bar, "qty": qty})
        if rule.get("raw_infer"):
            base = product["item"]
            candidates = ["Raw " + base]
            if base.startswith("Cooked "):
                candidates.append("Raw " + base[len("Cooked "):])
            materials = [{"item": c, "qty": 1} for c in candidates]
        if not materials:
            continue
        members = None
        if members_i is not None and members_i < len(row) and row[members_i]:
            mtxt = cell_text(row[members_i]).lower()
            members = "members" in mtxt and "free" not in mtxt
        rows_out.append({
            "skill": skill, "level": level, "product": product,
            "materials": materials, "members": members, "tools": tools,
            "source": page_title, "section": section,
        })
    return rows_out


def main():
    parser = TableCollector()
    all_recipes = []
    for page_title, skill in PAGES:
        try:
            got = harvest_page(page_title, skill, parser)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {page_title}: {e}")
            continue
        print(f"{page_title}: {len(got)} recipes")
        all_recipes.extend(got)
    # Preserve curated fields from an existing file (xp, fee, note, tools,
    # facilities) - the wiki harvest carries name/level/materials only.
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            keep = {r["id"]: r for r in json.load(f).get("recipes", [])}
        for r in all_recipes:
            o = keep.get(r["id"]) or keep.get(r.get("name"))
            if not o:
                continue
            for k in ("xp", "fee", "note", "tools", "facilities"):
                if o.get(k) is not None and r.get(k) is None:
                    r[k] = o[k]
    except Exception:
        pass
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"source": "wiki skill guide pages", "recipes": all_recipes}, f, indent=1)
    print(f"total {len(all_recipes)} -> {OUT_PATH}")


if __name__ == "__main__":
    main()
