import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent

# --- OSRS Wiki Real-time Prices API ---
# https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices
# The site itself runs fully client-side on GitHub Pages (browsers can't set a
# User-Agent). This UA is only sent by the local pipeline scripts below.
WIKI_BASE = "https://prices.runescape.wiki/api/v1/osrs"
USER_AGENT = "osrs_arb - profit finder dev build (contact: change-me@example.com)"

STALE_SECS = 15 * 60  # /latest older than this -> fall back to window averages

# --- Grand Exchange tax (change here if Jagex tweaks it) ---
GE_TAX_RATE = 0.02
# Tax = floor(price * rate), cap per item. floor() makes it < 1 coin below 50 gp,
# which the wiki treats as no tax obligation; 50 gp itself IS taxed (1 coin).
GE_TAX_EXEMPT_BELOW = 50
GE_TAX_CAP = 5_000_000

# --- Paths ---
DATA_DIR = BACKEND_ROOT / "data"
RECIPES_DIR = DATA_DIR / "recipes"                         # source of truth (item names), one <skill>.json per skill
HARVESTED_PATH = DATA_DIR / "harvested_raw.json"           # raw wiki harvest (merge_harvested input)
SITE_DATA_DIR = PROJECT_ROOT / "data"                      # baked artifacts served by Pages
SITE_ITEMS_PATH = SITE_DATA_DIR / "items.json"             # baked item metadata (id -> name/image/limit/value/members)
SITE_RECIPES_DIR = SITE_DATA_DIR / "recipes"               # baked per-skill recipe arrays
SITE_RECIPES_INDEX = SITE_RECIPES_DIR / "index.json"       # baked manifest: {generated, skills}
MAPPING_CACHE = PROJECT_ROOT / "var" / "mapping.json"      # /mapping cache for offline re-bakes
FIXTURES_PATH = BACKEND_ROOT / "tests" / "fixtures.json"   # parity fixtures (committed)
