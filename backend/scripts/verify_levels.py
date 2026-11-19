"""Grep production-level rows out of wiki skill guide pages to verify recipe levels."""
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://oldschool.runescape.wiki/api.php"

PAGES = {
    "smithing": "Smithing",
    "cooking": "Cooking",
    "crafting": "Crafting",
    "fletching": "Fletching",
    "magic": "Magic",
}

NAMES = [
    # smithing
    "Bronze bar", "Iron bar", "Silver bar", "Steel bar", "Gold bar", "Mithril bar",
    "Adamant bar", "Rune bar", "Bronze arrowtips", "Iron arrowtips", "Steel arrowtips",
    "Mithril arrowtips", "Adamant arrowtips", "Rune arrowtips", "Cannonball",
    # cooking
    "Shrimp", "Sardine", "Anchovies", "Herring", "Trout", "Salmon", "Tuna",
    "Lobster", "Swordfish", "Jug of wine",
    # crafting
    "Leather", "Hard leather", "Bow string", "Green dragon leather", "Blue dragon leather",
    "Green d'hide vambraces", "Green d'hide chaps", "Green d'hide body",
    "Blue d'hide vambraces", "Blue d'hide chaps", "Blue d'hide body",
    "Sapphire ring", "Sapphire necklace", "Sapphire amulet", "Molten glass",
    # fletching
    "Arrow shaft", "Headless arrow", "Bronze arrow", "Iron arrow", "Steel arrow",
    "Mithril arrow", "Adamant arrow", "Rune arrow",
    "Shortbow", "Longbow", "Oak shortbow", "Oak longbow", "Willow shortbow",
    "Willow longbow", "Maple shortbow", "Maple longbow", "Yew shortbow",
    "Yew longbow", "Magic shortbow", "Magic longbow",
    # magic (enchant)
    "Ring of recoil", "Ring of dueling", "Ring of forging", "Amulet of magic",
    "Amulet of defence", "Amulet of strength", "Necklace of passage", "Cosmic rune",
]


def wikitext(page: str) -> str:
    url = BASE + "?" + urllib.parse.urlencode(
        {"action": "parse", "page": page, "prop": "wikitext", "format": "json", "formatversion": "2"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "osrs_arb level verifier (contact: dev)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data["parse"]["wikitext"]


def main() -> None:
    for skill, page in PAGES.items():
        try:
            text = wikitext(page)
        except Exception as e:  # noqa: BLE001
            print(f"== {skill}: FAILED {e}")
            continue
        print(f"== {skill} ({len(text)} chars)")
        for line in text.splitlines():
            s = line.strip()
            if not s.startswith("|"):
                continue
            low = s.lower()
            for name in NAMES:
                if name.lower() in low:
                    row = re.sub(r"\{\{[^}]*\}\}", " ", s)  # collapse templates for readability
                    row = re.sub(r"\s+", " ", row).strip("| ")
                    print(f"  [{name}] {row[:240]}")
                    break


if __name__ == "__main__":
    sys.exit(main())
