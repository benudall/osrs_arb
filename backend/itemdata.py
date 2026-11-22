"""Item metadata: wiki image URLs, /mapping fetch + indexes (DB-free)."""
import json
import re
import time
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
