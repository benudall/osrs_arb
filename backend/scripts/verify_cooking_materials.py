"""Verify cooking recipe materials against OSRS wiki item pages.

Ground truth = the {{Recipe}} template(s) on each product's wiki item page:
- |mat1..N|/|matNquantity| (legacy |matNqty|) = the final combine step's
  materials (authoritative). mat indexes may gap (mat1, mat3, ...)
- when the page carries an {{Instructions}} template, links from its FINAL
  step that appear nowhere earlier and not in the mats are garnish added
  at the finish step (e.g. equa leaves on cheese+tom batta) and are counted
- |tools = X| / known reusable tools / facilities (range, vat, press, ...)
  are not materials
- gnome dough / gianne dough = pot of flour + bucket of water (page has no
  {{Recipe}} template, quantities fixed by the Gnome cooking guide)
- a mat name may carry a variant fragment ([[incomplete stew#Potato]]):
  the fragment selects which alternative template on the fragment's page
  to expand into

Expected materials are reduced recursively: a material absent from the
recipe, without a live GE price, is replaced by the {{Recipe}} mats of its
own wiki page (dataset recipe mats as fallback). Keys present in the
recipe are never reduced — the dataset may legitimately keep an unpriced
intermediate it can craft in-app (pitta dough, tuna and corn, ...), and a
priced intermediate is never expanded (that would hide stale expansions
like the old pie_shell flour+water entry).

Equivalences tolerated when matching:
- water vessel (bucket/bowl/jug of water) -> one WATER slot
- raw meat sources (beef/bear/boar/rat/yak/impaler) -> one RAW_MEAT slot
- pineapple ring vs chunks

Usage (from backend/):  python scripts/verify_cooking_materials.py [--skill cooking]
"""
import json
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, ".")
import config  # noqa: E402
import recipes as recipes_mod  # noqa: E402

UA = "osrs_arb recipe verifier (contact: dev)"

# reusable tools (not consumed). NB: pie dish and cake tin are NOT here —
# the wiki templates list them as consumed materials. Gnome spice is not
# hardcoded either: the wiki tags it |tools = on gnome recipes but lists it
# as a consumed mat on Spicy sauce.
TOOLS = {"crunchy tray", "batta tin", "gnomebowl mould", "cocktail shaker",
         "knife", "churn", "pestle and mortar", "iron spit"}
FACILITIES = {"range", "cooking range", "fire", "brewery", "oven",
              "apple press", "fermenting vat", "ogre spit-roast",
              "cooking range or fire"}
WATER = {"bucket of water", "bowl of water", "jug of water"}
RAW_MEAT = {"raw beef", "raw bear meat", "raw boar meat", "raw rat meat",
            "raw yak meat", "raw impaler meat", "raw meat"}
DOUGHS = {"gnome dough", "gianne dough"}  # = pot of flour + bucket of water
ALIASES = {
    "toad legs": "Toad's legs",
    "toad's legs": "Toad's legs",
    "equa leaf": "Equa leaves",
    "chocolate dust": "Chocolate dust",
    "gnome spice": "Gnome spice",
    "equa leaves": "Equa leaves",
    "king worm": "King worm",
    "pot of cream": "Pot of cream",
    "dwellberries": "Dwellberries",
    "cocktail glass": "Cocktail glass",
    "onion & tomato": "Onion & tomato",
    "zamorak's grapes": "Zamorak's grapes",
    "sweetcorn (bowl)": "Sweetcorn (bowl)",
    "cooked sweetcorn": "Cooked sweetcorn",
    "curry leaf": "Curry leaf",
    "curry leaves": "Curry leaf",
    "pitta bread": "Pitta bread",
    "spicy sauce": "Spicy sauce",
    "chopped garlic": "Chopped garlic",
    "chopped onion": "Chopped onion",
    "sliced mushrooms": "Sliced mushrooms",
    "scrambled egg": "Scrambled egg",
    "uncooked egg": "Uncooked egg",
    "baked potato": "Baked potato",
    "pat of butter": "Pat of butter",
    "potato with butter": "Potato with butter",
    "egg and tomato": "Egg and tomato",
    "chilli con carne": "Chilli con carne",
    "fried onions": "Fried onions",
    "fried mushrooms": "Fried mushrooms",
    "mushroom & onion": "Mushroom & onion",
    "tuna and corn": "Tuna and corn",
    "kebab mix": "Kebab mix",
    "ugthanki meat": "Ugthanki meat",
    "raw ugthanki meat": "Raw ugthanki meat",
    "uncooked stew": "Uncooked stew",
    "uncooked curry": "Uncooked curry",
    "uncooked pizza": "Uncooked pizza",
    "uncooked cake": "Uncooked cake",
    "uncooked berry pie": "Uncooked berry pie",
    "uncooked apple pie": "Uncooked apple pie",
    "uncooked meat pie": "Uncooked meat pie",
    "uncooked mushroom pie": "Uncooked mushroom pie",
    "uncooked botanical pie": "Uncooked botanical pie",
    "uncooked dragonfruit pie": "Uncooked dragonfruit pie",
    "raw mud pie": "Raw mud pie",
    "raw garden pie": "Raw garden pie",
    "raw fish pie": "Raw fish pie",
    "raw admiral pie": "Raw admiral pie",
    "raw wild pie": "Raw wild pie",
    "raw summer pie": "Raw summer pie",
    "raw oomlie": "Raw oomlie",
    "palm leaf": "Palm leaf",
    "wrapped oomlie": "Wrapped oomlie",
    "leaping trout": "Leaping trout",
    "leaping sturgeon": "Leaping sturgeon",
    "sacred eel": "Sacred eel",
    "raw karambwanji": "Raw karambwanji",
    "leechfin": "Leechfin",
    "raw lava eel": "Raw lava eel",
    "seaweed": "Seaweed",
    "bucket of milk": "Bucket of milk",
    "pot of flour": "Pot of flour",
    "grapes": "Grapes",
    "ale yeast": "Ale yeast",
    "barley malt": "Barley malt",
    "beer glass": "Beer glass",
    "beer glasses": "Beer glass",
    "hammerstone hops": "Hammerstone hops",
    "asgarnian hops": "Asgarnian hops",
    "harralander": "Harralander",
    "yanillian hops": "Yanillian hops",
    "krandorian hops": "Krandorian hops",
    "wildblood hops": "Wildblood hops",
    "mushroom": "Mushroom",
    "cooking apple": "Cooking apple",
    "bucket": "Bucket",
    "spider on stick (raw)": "Spider on stick (raw)",
    "spider on shaft (raw)": "Spider on shaft (raw)",
    "raw stuffed snake": "Raw stuffed snake",
    "raw chompy": "Raw chompy",
    "raw jubbly": "Raw jubbly",
    "raw pyre fox": "Raw pyre fox",
    "raw sunlight antelope": "Raw sunlight antelope",
    "raw moonlight antelope": "Raw moonlight antelope",
    "raw larupia": "Raw larupia",
    "raw graahk": "Raw graahk",
    "raw kyatt": "Raw kyatt",
    "raw barb-tailed kebbit": "Raw barb-tailed kebbit",
    "raw wild kebbit": "Raw wild kebbit",
    "raw dashing kebbit": "Raw dashing kebbit",
    "raw t-bone steak": "Raw t-bone steak",
    "thin snail": "Thin snail",
    "lean snail": "Lean snail",
    "fat snail": "Fat snail",
    "raw bream": "Raw bream",
    "raw slimy eel": "Raw slimy eel",
    "raw karambwan": "Raw karambwan",
    "raw cavefish": "Raw cavefish",
    "raw catfish": "Raw catfish",
    "raw tetra": "Raw tetra",
    "raw guppy": "Raw guppy",
    "raw pysk fish (0)": "Raw pysk fish (0)",
    "raw pysk fish": "Raw pysk fish (0)",
    "raw suphi fish (1)": "Raw suphi fish (1)",
    "raw leckish fish (2)": "Raw leckish fish (2)",
    "raw brawk fish (3)": "Raw brawk fish (3)",
    "raw mycil fish (4)": "Raw mycil fish (4)",
    "raw roqed fish (5)": "Raw roqed fish (5)",
    "raw kyren fish (6)": "Raw kyren fish (6)",
}

WORD_QTY = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
            "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def norm(name: str) -> str:
    s = name.strip().lower().replace("\u2019", "'")
    s = re.sub(r"\s+", " ", s)
    s = s.split("#")[0].strip()  # link fragments: [[incomplete stew#potato]]
    return ALIASES.get(s, s)


def canon(normed: str) -> str:
    """Collapse equivalences for matching."""
    if normed in WATER:
        return "WATER"
    if normed in RAW_MEAT:
        return "RAW_MEAT"
    if normed in ("pineapple ring", "pineapple chunks"):
        return "PINEAPPLE"
    return normed


def title_for_wiki(normed: str) -> str:
    """Best-effort page title for a normed name; redirects fix the rest."""
    proper = ALIASES.get(normed)
    if proper:
        return proper
    return normed[:1].upper() + normed[1:]


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_pages(titles: list[str]) -> dict[str, str]:
    out = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        url = ("https://oldschool.runescape.wiki/api.php?" + urllib.parse.urlencode(
            {"action": "query", "titles": "|".join(batch), "prop": "revisions",
             "rvprop": "content", "rvslots": "main", "format": "json",
             "formatversion": "2", "redirects": "1"}))
        for p in fetch_json(url)["query"]["pages"]:
            if "revisions" in p:
                out[p["title"]] = p["revisions"][0]["slots"]["main"]["content"]
    return out


TEMPLATE_RE = re.compile(r"\{\{(Recipe|Instructions)\s*(.*?)\n\}\}", re.S)


def parse_steps(body: str) -> list[tuple[int, str]]:
    steps = []
    for sm in re.finditer(r"\|\s*step(\d+)\s*=\s*([^|\n]*(?:\n(?!\|)[^|\n]*)*)", body):
        steps.append((int(sm.group(1)), sm.group(2).strip()))
    steps.sort()
    return steps


def parse_page(wikitext: str) -> dict:
    """All {{Recipe}} blocks (alternatives kept separate) + {{Instructions}}."""
    instr_steps: list[str] = []
    recipes = []
    for m in TEMPLATE_RE.finditer(wikitext):
        kind, body = m.group(1), m.group(2)
        tm = re.search(r"\|\s*tools\s*=\s*([^|\n]+)", body)
        tools = {norm(t).lower() for t in tm.group(1).split(",")} if tm else set()
        if kind == "Instructions":
            instr_steps.extend(s for _, s in parse_steps(body))
            continue
        mats = []
        idx = 1
        while idx <= 12:  # indexes may gap (mat1, mat3, ...): never break early
            nm = re.search(rf"\|\s*mat{idx}\s*=\s*([^|\n]+)", body)
            if nm:
                raw_name = re.sub(r"\}\}\s*$", "", nm.group(1)).strip()
                qm = re.search(rf"\|\s*mat{idx}quantity\s*=\s*([^|\n]+)", body) \
                    or re.search(rf"\|\s*mat{idx}qty\s*=\s*([^|\n]+)", body)
                qty = 1
                if qm:
                    qn = re.search(r"\d+", qm.group(1))
                    if qn:
                        qty = int(qn.group(0))
                mats.append((raw_name, qty))
            idx += 1
        raw_outputs = []
        oi = 1
        while oi <= 12:
            om = re.search(rf"\|\s*output{oi}\s*=\s*([^|\n]+)", body)
            if om:
                raw_outputs.append(re.sub(r"\}\}\s*$", "", om.group(1)).strip())
            oi += 1
        recipes.append({"mats": mats, "steps": [s for _, s in parse_steps(body)],
                        "raw_outputs": raw_outputs, "tools": tools})
    return {"instr_steps": instr_steps, "recipes": recipes}


LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def step_items(step: str) -> list[str]:
    return [t.strip() for t in LINK_RE.findall(step)]


def _link_spans(step: str) -> list[tuple[int, int]]:
    """[(start, end)] character spans of each wiki link in the step."""
    return [(m.start(), m.end()) for m in LINK_RE.finditer(step)]


def step_qty(step: str, link: str) -> int:
    """Number or word right before the link in the step text (default 1)."""
    target = link.split("|")[0].split("#")[0]
    sm = re.search(rf"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
                   rf"{re.escape(target)}", step, re.I)
    if sm:
        tok = sm.group(1).lower()
        return int(tok) if tok.isdigit() else WORD_QTY[tok]
    return 1


def merge(dst: dict, key: str, qty: int) -> None:
    dst[key] = dst.get(key, 0) + qty


def add_item(dst: dict, fragmap: dict, raw_name: str, qty: int) -> None:
    """Add one ingredient; doughs expand inline, fragments recorded.
    Burnt/ruined items are failure outcomes, never ingredients.
    Keys are lowercased (aliases may return proper case)."""
    normed = norm(raw_name)
    low = normed.lower()
    if low.startswith(("burnt ", "ruined ")):
        return
    if low in DOUGHS:  # gnome dough page has no {{Recipe}}: fixed inputs
        merge(dst, "pot of flour", qty)
        merge(dst, "WATER", qty)
        return
    key = canon(low)
    merge(dst, key, qty)
    if "#" in raw_name and key not in fragmap:
        fragmap[key] = raw_name.split("#", 1)[1].strip()


def expected_candidates(page: dict, product_norm: str) -> list[dict[str, int]]:
    """One expected-materials dict per {{Recipe}} alternative."""
    cands = []
    product_low = product_norm.lower()
    page_tools: set[str] = set()
    for b in page["recipes"]:
        page_tools.update(b["tools"])
    prior_links: set[str] = set()
    garnish: list[tuple[str, int]] = []
    if page["instr_steps"]:
        steps = page["instr_steps"]
        all_links = [step_items(s) for s in steps]
        for links in all_links[:-1]:  # earlier steps only — the final step's
            for x in links:           # own links must stay garnish-eligible
                prior_links.add(norm(x).lower())
        last = all_links[-1]
        last_step = steps[-1]
        # "or"-joined links in the final step are variant alternatives
        # ("chocolate bar or chocolate dust"), not additive garnish
        alternative: set[int] = set()
        pos = 0
        for i, x in enumerate(last):
            start = last_step.find("[[", pos)
            end = last_step.find("]]", start) + 2 if start >= 0 else pos
            gap = last_step[end:last_step.find("[[", end) if last_step.find("[[", end) >= 0 else len(last_step)]
            if re.search(r",?\s+or\s+(?:an?\s+|the\s+)?$", gap):
                alternative.update({i, i + 1})
            pos = end
        for i, (x, span) in enumerate(zip(last, _link_spans(last_step))):
            # finish-step garnish (equa leaves etc.)
            if i in alternative:
                continue
            # links introduced as the step's output ("... to make a [[mud pie]]")
            # are the next product down the chain, not an ingredient
            pre = last_step[:span[0]]
            if re.search(r"to\s+(?:make|create|finish|cook|bake|become)\s+(?:an?\s+|the\s+|1\s+)?$", pre, re.I):
                continue
            nx = norm(x).lower()
            if nx in prior_links or nx in TOOLS or nx in FACILITIES \
                    or nx == product_low or nx in page_tools:
                continue
            garnish.append((x, step_qty(last_step, x)))
    for block in page["recipes"]:
        skip = TOOLS | FACILITIES | block["tools"] | {product_low}
        outputs = {norm(o).lower() for o in block["raw_outputs"]}
        expected: dict[str, int] = {}
        fragmap: dict[str, str] = {}
        for name, qty in block["mats"]:
            nn = norm(name).lower()
            if nn in outputs or nn in skip:
                continue
            add_item(expected, fragmap, name, qty)
        present = {k.lower() for k in expected}
        for raw, qty in garnish:
            if canon(norm(raw).lower()) in present:
                continue  # already counted from mats
            add_item(expected, fragmap, raw, qty)
        cands.append({"expected": expected, "fragmap": fragmap})
    return cands


class Expander:
    """Recursive reduction of unpriced intermediates to their wiki mats."""

    def __init__(self, price_names: set[str], dataset_products: dict[str, list[dict]]):
        self.price_names = price_names  # lowercased names with a live GE price
        self.dataset_products = dataset_products  # normed product -> mats
        self.pages: dict[str, dict | None] = {}

    def _page(self, title: str) -> dict | None:
        if title not in self.pages:
            w = fetch_pages([title]).get(title)
            self.pages[title] = parse_page(w) if w else None
        return self.pages[title]

    def expand(self, expected: dict[str, int], fragmap: dict[str, str],
               actual: dict[str, int], chain: tuple = (), depth: int = 0) -> dict[str, int]:
        if depth > 6:
            return expected
        todo = [k for k in expected
                if k not in actual and k not in ("WATER", "RAW_MEAT", "PINEAPPLE")
                and k not in chain
                and k.lower() not in self.price_names
                and k.lower() not in DOUGHS]
        if not todo:
            return expected
        titles = sorted({title_for_wiki(k) for k in todo})
        for t in titles:
            self._page(t)
        out: dict[str, int] = {}
        for k, qty in expected.items():
            if k in todo:
                mats = self.dataset_products.get(k.lower())
                if mats is None:
                    page = self._page(title_for_wiki(k))
                    block = self._select_block(page, fragmap.get(k)) if page else None
                    if block:
                        mats = []
                        skip = TOOLS | FACILITIES | block["tools"]
                        outputs = {norm(o).lower() for o in block["raw_outputs"]}
                        for name, q in block["mats"]:
                            nn = norm(name).lower()
                            if nn in outputs or nn in skip:
                                continue
                            mats.append((name, q))
                if mats:
                    for name, q in mats:
                        add_item(out, fragmap, name, q * qty)
                    continue
            out[k] = out.get(k, 0) + qty
        if out == expected:
            return expected
        return self.expand(out, fragmap, actual, chain + tuple(todo), depth + 1)

    @staticmethod
    def _select_block(page: dict, fragment: str | None) -> dict | None:
        blocks = page["recipes"]
        if not blocks:
            return None
        if fragment and len(blocks) > 1:
            frag = fragment.lower()
            for b in blocks:
                if any(frag in o.lower() for o in b["raw_outputs"]):
                    return b
        return blocks[0]


def load_price_names() -> set[str]:
    """Lowercased names of items with a live GE price right now."""
    try:
        mapping = json.loads(config.MAPPING_CACHE.read_text(encoding="utf-8"))
        id_to_name = {int(m["id"]): m["name"] for m in mapping}
        latest = fetch_json(config.WIKI_BASE + "/latest")["data"]
        return {id_to_name[int(i)].lower() for i in latest if int(i) in id_to_name}
    except Exception as e:
        print(f"  (price lookup unavailable: {e}; falling back to mapping names)")
        try:
            mapping = json.loads(config.MAPPING_CACHE.read_text(encoding="utf-8"))
            return {m["name"].lower() for m in mapping}
        except Exception:
            return set()


def load_dataset_products() -> dict[str, list[dict]]:
    """normed product name -> mats, for recipes that can craft it in-app."""
    out = {}
    for r in recipes_mod.load_recipes(config.RECIPES_DIR):
        out.setdefault(r["product"]["item"].lower(),
                       [(m["item"], m["qty"]) for m in r["materials"]])
    return out


def main() -> int:
    skill = "cooking"
    if "--skill" in sys.argv:
        skill = sys.argv[sys.argv.index("--skill") + 1]
    recipes = [r for r in recipes_mod.load_recipes(config.RECIPES_DIR) if r["skill"] == skill]

    products = sorted({r["product"]["item"] for r in recipes})
    pages = {t: parse_page(w) if w else None for t, w in fetch_pages(products).items()}
    expander = Expander(load_price_names(), load_dataset_products())

    ok, bad, norecipe = [], [], []
    for r in recipes:
        prod = r["product"]["item"]
        page = pages.get(prod)
        actual = {}
        for m in r["materials"]:
            add_item(actual, {}, m["item"], m["qty"])
        if page is None:
            norecipe.append((r["id"], prod, "page not found"))
            continue
        cands = expected_candidates(page, norm(prod))
        if not cands:
            norecipe.append((r["id"], prod, "no {{Recipe}} template"))
            continue
        expanded = [expander.expand(dict(c["expected"]), dict(c["fragmap"]), actual)
                    for c in cands]
        if any(c == actual for c in expanded):
            ok.append(r["id"])
        else:
            best = min(expanded, key=lambda c: sum(
                abs((c.get(k, 0) or 0) - (actual.get(k, 0) or 0))
                + (0 if (c.get(k, 0) or 0) and (actual.get(k, 0) or 0) else 1)
                for k in set(c) | set(actual)))
            keys = sorted(set(best) | set(actual))
            diffs = [f"{k}: expected {best.get(k, 0)} got {actual.get(k, 0)}"
                     for k in keys if best.get(k, 0) != actual.get(k, 0)]
            bad.append((r["id"], prod, "; ".join(diffs)))

    print(f"{len(ok)} OK, {len(bad)} MISMATCH, {len(norecipe)} unverifiable "
          f"(of {len(recipes)} {skill} recipes)")
    print("\n== MISMATCHES ==")
    for rid, prod, diffs in bad:
        print(f"  {rid} ({prod}): {diffs}")
    print("\n== UNVERIFIABLE ==")
    for rid, prod, why in norecipe:
        print(f"  {rid} ({prod}): {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
