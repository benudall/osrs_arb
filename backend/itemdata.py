"""Item metadata: wiki image URLs, /mapping fetch + indexes (DB-free)."""
import json
import math
import re
import time
import urllib.parse
import urllib.request

import config

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
    "Bronze bolts (unf)": "_5",
    "Bronze bolts": "_5",
    "Bronze brutal": "_5",
    "Bronze javelin tips": "_5",
    "Burning amulet(5)": "",
    "Castle wars bracelet(3)": "",
    "Cooked giant crab meat": "_(5)",
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
    "Iron javelin tips": "_5",
    "Jade bolt tips": "_5",
    "Javelin shaft": "_5",
    "Lava scale shard": "_5",
    "Mithril arrow": "_5",
    "Mithril bolts (unf)": "_5",
    "Mithril bolts": "_5",
    "Mithril brutal": "_5",
    "Mithril javelin tips": "_5",
    "Moonlight antler bolts": "_5",
    "Ogre arrow shaft": "_5",
    "Onyx bolt tips": "_5",
    "Onyx bolts": "_5",
    "Opal bolt tips": "_5",
    "Opal bolts": "_5",
    "Opal dragon bolts": "_5",
    "Ring of returning": "",
    "Ruby bolt tips": "_5",
    "Ruby bolts": "_5",
    "Rune arrow": "_5",
    "Rune brutal": "_5",
    "Rune javelin tips": "_5",
    "Runite bolts (unf)": "_5",
    "Runite bolts": "_5",
    "Sapphire bolt tips": "_5",
    "Sapphire bolts": "_5",
    "Silver bolts (unf)": "_5",
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


def image_url(name: str) -> str:
    """Wiki image URL for an item, handling overrides and special cases."""
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


WIKI_META_CACHE = config.PROJECT_ROOT / "var" / "wiki_meta.json"

INFOBOX_RE = re.compile(r"\{\{Infobox Item(.*?)\n\}\}", re.S)


def _parse_infobox(wikitext: str, title: str | None = None) -> dict | None:
    """Extract item metadata from an OSRS wiki item page infobox.

    Handles multi-version infoboxes (|name1/|id1/|defver = ...): the version
    whose |nameN matches the requested page title wins, else the |defver
    version, else the first listed version. Plain single-version pages are
    unaffected.
    """
    m = INFOBOX_RE.search(wikitext)
    if not m:
        return None
    fields = {}
    for line in m.group(1).split("\n"):
        fm = re.match(r"\|\s*([a-z0-9_]+)\s*=\s*(.*)", line)
        if fm:
            fields[fm.group(1)] = fm.group(2).strip()

    def _int(key):
        raw = fields.get(key)
        if raw is None:
            return None
        im = re.search(r"-?\d[\d,]*", raw.replace(",", ""))
        return int(im.group(0)) if im else None

    # version selection for multi-version infoboxes (no plain |id)
    if _int("id") is None:
        versions = sorted(int(vm.group(1)) for key in fields
                          if (vm := re.match(r"id(\d+)$", key)))
        if versions:
            pick = None
            if title:
                for n in versions:
                    if fields.get(f"name{n}", "").strip().lower() == title.strip().lower():
                        pick = n
                        break
            if pick is None:
                dv = _int("defver")
                pick = dv if dv in versions else versions[0]
            fields["id"] = fields[f"id{pick}"]
            fields["name"] = fields.get(f"name{pick}") or fields.get("name")
            fields["members"] = fields.get("members") or fields.get(f"members{pick}", "")
            fields["tradeable"] = fields.get("tradeable") or fields.get(f"tradeable{pick}", "")

    image_file = None
    im = re.search(r"\[\[File:([^\]|]+?\.png)", fields.get("image", "") or "")
    if im:
        image_file = im.group(1)
    return {
        "name": fields.get("name"),
        "id": _int("id"),
        "value": _int("value"),
        "highalch": _int("highalch"),
        "members": (fields.get("members", "").lower() == "yes"),
        "tradeable": (fields.get("tradeable", "").lower() == "yes"),
        "image_file": image_file,
    }


def fetch_wiki_meta(names: list[str], force: bool = False) -> dict:
    """Metadata for items missing from /mapping (no GE price history), parsed
    from their OSRS wiki item infoboxes: {name: {id, name, members, value,
    highalch, tradeable, image_file} | None}. Pages without an id (or missing
    entirely) cache as None. Cached 24h in var/wiki_meta.json.
    """
    cache = WIKI_META_CACHE
    data = {}
    if not force and cache.exists():
        age = time.time() - cache.stat().st_mtime
        if age < 24 * 3600:
            data = json.loads(cache.read_text(encoding="utf-8"))
    todo = [n for n in names if n not in data]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?" + urllib.parse.urlencode(
            {"action": "query", "titles": "|".join(batch), "prop": "revisions",
             "rvprop": "content", "rvslots": "main", "format": "json",
             "formatversion": "2"}))
        req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
        for p in d["query"]["pages"]:
            title = p["title"]
            meta = None
            if "revisions" in p:
                meta = _parse_infobox(p["revisions"][0]["slots"]["main"]["content"], title)
                if meta and not meta.get("id"):
                    meta = None
            data[title] = meta
    if todo:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def fallback_item_map_entry(meta: dict, display_name: str | None = None) -> dict:
    """item_map entry for a wiki-infobox-only item (no /mapping data).
    buy_limit is unknown -> None (FE shows no 4h cap). value falls back to
    highalch/0.6 so floor(value * 0.6) reproduces the high alch payout.
    display_name overrides the infobox name when the page title is the more
    precise item name (e.g. 'Spider on stick (raw)' vs infobox 'Spider on stick')."""
    name = display_name or meta.get("name") or ""
    value = meta.get("value")
    if value is None and meta.get("highalch") is not None:
        value = math.ceil(meta["highalch"] / 0.6)
    image_file = meta.get("image_file")
    if image_file:
        image = image_url(image_file.rsplit(".png", 1)[0])
    else:
        image = image_url(name)
    return {
        "id": int(meta["id"]),
        "name": name,
        "members": bool(meta.get("members")),
        "buy_limit": None,
        "value": value,
        "image_url": image,
    }


def fetch_mapping(force: bool = False) -> list[dict]:
    """Fetch /mapping (the wiki's item list: id, name, members, limit, value).

    Cached to var/mapping.json for 24h so recipe work doesn't need network
    every run. force=True refetches.
    """
    cache = config.MAPPING_CACHE
    if not force and cache.exists():
        age = time.time() - cache.stat().st_mtime
        if age < 24 * 3600:
            return json.loads(cache.read_text(encoding="utf-8"))
    req = urllib.request.Request(
        config.WIKI_BASE + "/mapping", headers={"User-Agent": config.USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def index_mapping(mapping: list[dict]):
    """-> (name_to_id, item_map).

    item_map[id] = {id, name, members, buy_limit, value, image_url} — the
    shape profit.py expects.
    """
    name_to_id, item_map = {}, {}
    for m in mapping:
        mid = int(m["id"])
        name_to_id[m["name"]] = mid
        item_map[mid] = {
            "id": mid,
            "name": m["name"],
            "members": bool(m.get("members")),
            "buy_limit": m.get("limit"),
            "value": m.get("value"),
            "image_url": image_url(m["name"]),
        }
    return name_to_id, item_map
