import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

# --- Wiki Real-time Prices API ---
# https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices
# A descriptive User-Agent is REQUIRED. Put real contact info here.
WIKI_BASE = "https://prices.runescape.wiki/api/v1/osrs"
USER_AGENT = "osrs_arb - profit finder dev build (contact: change-me@example.com)"

REFRESH_SECS = 60          # background /latest + /5m poll
MAPPING_TTL_SECS = 24 * 3600
STALE_SECS = 15 * 60       # /latest older than this -> fall back to window averages

# --- Grand Exchange tax (change here if Jagex tweaks it) ---
GE_TAX_RATE = 0.02
GE_TAX_EXEMPT_MAX = 50    # items selling at <= this many gp are tax-exempt
GE_TAX_CAP = 5_000_000     # per-item cap

# --- Storage ---
DB_PATH = PROJECT_ROOT / "var" / "osrs_arb.sqlite"
RECIPES_PATH = BACKEND_ROOT / "data" / "recipes.json"

HISCORES_URL = "https://services.runescape.com/m=hiscore_oldschool/index_lite.json"
HISCORES_TTL_SECS = 300
