# OSRS Arb

Buy materials off the GE → craft → sell product. Finds profitable recipes for your skill levels.

**Pure Python.** FastAPI + SQLite backend serves a vanilla JS UI from the same origin —
no node, no npm, no build step.

- Backend: Python / FastAPI / SQLite (`backend/`)
- UI: static files served by FastAPI (`backend/app/web/static/` — plain HTML/JS/CSS)
- Prices: OSRS Wiki Real-time Prices API (needs a descriptive User-Agent — set it in `backend/app/config.py`)
- Recipes: curated in `backend/data/recipes.json` (item names; resolved to ids at seed)

## Resources

- **[OSRS Wiki Real-time Prices API](https://prices.runescape.wiki/api/v1/osrs)**: Used for real-time item price data and market volume.
- **[OSRS Hiscores API](https://services.runescape.com/m=hiscore_oldschool/index_lite.json)**: Used to fetch player skill levels for automatic recipe filtering.

## Setup

One command (or double-click `start.bat`):

```bash
python run.py
```

First run creates the venv and installs deps automatically, then serves UI + API at
http://127.0.0.1:8000/ (open it yourself; add `--browser` to auto-open). Flags:
`--setup` (reinstall deps), `--port N`, `--browser`.

Manual equivalent:

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Windows
# .venv/bin/pip install -r requirements.txt       # Linux/macOS
.venv/Scripts/python -m pytest                    # unit tests (profit math)
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

On startup the server: fetches `/mapping` into SQLite, seeds `recipes.json`, then polls
`/latest` + `/5m` + `/1h` every 60 s into `var/osrs_arb.sqlite` (gitignored).

Endpoints: `GET /api/skills`, `GET /api/recipes`, `GET /api/meta`,
`GET /api/hiscores?player=NAME`, `POST /api/admin/reseed`, `POST /api/admin/refresh-mapping`
(admin POSTs are unauthenticated — the tool is meant to run on localhost only).
Docs at http://127.0.0.1:8000/docs.

CLI: `python -m scripts.seed_recipes` (seed only). `python scripts/verify_levels.py`
prints recipe-level rows from the wiki skill guides for spot-checking.

### Recipe harvesting pipeline

Recipes come from two sources: the curated `recipes.json` entries (hand-checked) and
a bulk harvest of the wiki skill guide pages (Smithing, Cooking, Crafting, Fletching,
Herblore + the seven Lvl-N Enchant spell pages):

```bash
python scripts/harvest_recipes.py    # wiki HTML tables -> data/harvested_raw.json
python scripts/merge_harvested.py    # resolve names, dedupe vs curated, append
python -m scripts.seed_recipes       # reload into SQLite
```

Merge keeps curated recipes on conflict, resolves names against the GE item mapping
(incl. potion dose suffixes like `Attack potion(3)` and charged jewellery like
`Ring of dueling(8)`), and skips quest/minigame-only items that aren't on the GE.
Levels for harvested recipes come straight from the wiki tables.

## Features

- Per-skill level inputs (persisted in localStorage, or fetched from hiscores by player name)
- Free-text search (product / materials / skill, all words must match)
- Conservative/optimistic margin modes, f2p filter, min-volume gate
- Sortable table: product, materials, cost, gross, net, net%, volume, 4h count, member badge
- Expandable row detail: per-material breakdown + tax + buy-limit math + recipe notes
- Auto-refresh every 30 s, stale-price marker (≈)

## Notes

- `high` = price buyers pay (you buy materials at `high`), `low` = price sellers get.
  Conservative mode = buy `high` / sell `low` (all instant). Optimistic = the reverse.
- Cost/Net use the **cheapest acquisition** per material — buy it, or craft it if that is
  cheaper (⚒ in the materials column). `cost` = Σ cheapest-per-material × qty + fees, `net` = gross − tax − cost.
- GE tax 2% (exempt < 50 gp, cap 5 m/item) — `backend/app/config.py`.
- Buy limits cap real profit: `count` column = max crafts per 4 h, `net_4h` in row detail.
- Volume gate (5 m trade volume of the scarcest ingredient) hides illiquid "ghost profits".
- Recipe **levels**: cooking verified against the wiki guide; smithing/crafting/fletching/herblore/magic
  levels now come from the wiki skill pages via the harvest pipeline. Curated-entry levels are memory-based
  and win over harvested ones — spot-check with `scripts/verify_levels.py` if in doubt. Yields are wiki-checked.
