# OSRS Arb

Buy materials off the GE → craft → sell product. Finds profitable recipes for your skill levels.

**Fully static.** Vanilla JS served by GitHub Pages — no backend, no database, no build step.
Prices are pulled client-side from the OSRS Wiki Real-time Prices API (CORS-open); recipes and
item metadata are baked into `data/recipes.json` at repo-bake time.

- UI: `index.html` + `app.js` + `styles.css` (plain HTML/JS/CSS, no framework)
- Profit math: `profit.js` + `pricestore.js` (browser globals, also loadable in node)
- Baked site data: `data/recipes.json` (generated — do not edit by hand)
- Python tooling: `backend/` (recipe pipeline, tests, parity harness)

## Data flow

```
repo bake time (python)                 browser (runtime)
───────────────────────                 ──────────────────────────────
backend/data/recipes.json   ──bake──▶   data/recipes.json  (ids, names, images,
  (item names, hand-editable)               buy limits, values — static)
                                        + wiki /latest /5m /1h  every 60s  (live prices)
                                        → evaluate all recipes in JS → table
```

The baked file is self-contained: the browser never fetches `/mapping`. Only prices are live.
Hiscores lookup was dropped (CORS-blocked, no backend anymore) — enter levels manually; they
persist in localStorage.

## Resources

- **[OSRS Wiki Real-time Prices API](https://prices.runescape.wiki/api/v1/osrs)**: live prices
  + volumes. CORS-open; the browser sends its own User-Agent (can't be overridden from JS —
  accepted tradeoff of a static site).
- Recipe data: curated in `backend/data/recipes.json` (item names), harvested from the wiki
  skill guide pages.

## Run locally

Any static file server from the repo root (a real server is needed because `fetch()` of local
JSON doesn't work from `file://`):

```bash
python -m http.server 8000
# open http://127.0.0.1:8000/
```

## Deploy (GitHub Pages)

Repo Settings → Pages → Deploy from branch → `main` / `(root)`. `.nojekyll` is already in place.
After re-baking data, users may need a hard refresh (Pages CDN caches); bump a `?v=` query in
`app.js`'s `data/recipes.json` fetch if staleness bites.

## Recipe pipeline (all Python, run from `backend/` with the venv active)

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # pytest only
.venv/Scripts/python -m pytest                    # profit-math unit tests

python scripts/harvest_recipes.py    # wiki HTML tables -> data/harvested_raw.json
python scripts/merge_harvested.py    # resolve names, dedupe vs curated, append
python scripts/bake_static.py        # data/recipes.json -> ../data/recipes.json (ids)
python scripts/verify_levels.py      # spot-check recipe levels vs wiki guides
```

- `backend/data/recipes.json` is the source of truth (item names; reviewable diffs).
- `bake_static.py` resolves names→ids, recomputes members flags, attaches wiki image URLs,
  and embeds every referenced item (name/image/buy-limit/value) so the site is self-contained.
- Merge keeps curated recipes on conflict, resolves dose suffixes (`Attack potion(3)`) and
  charged jewellery (`Ring of dueling(8)`), and skips quest/minigame-only items.

## JS ↔ Python parity

`profit.js` and `pricestore.js` are ports of `backend/profit.py` / `backend/pricestore.py`
(the Python files are the reference). The parity harness proves they agree:

```bash
cd backend
.venv/Scripts/python scripts/gen_fixtures.py    # live prices -> tests/fixtures.json (committed)
node scripts/parity_check.cjs                   # replay through JS, diff every row
```

Fixtures freeze the clock, trim wiki payloads to referenced items, and cover both margin
modes: every recipe row and every price resolution must match exactly. Re-run `gen_fixtures.py`
whenever the math or the baked data changes, and commit the refreshed fixtures.

## Notes

- `high` = price buyers pay (you buy materials at `high`), `low` = price sellers get.
  Conservative pricing is baked in: buy `high` / sell `low` (all instant).
- Cost/Net use the **cheapest acquisition** per material — buy it, or craft it if that is
  cheaper (⚒ in the materials column). `cost` = Σ cheapest-per-material × qty + fees,
  `net` = gross − tax − cost.
- GE tax 2% (exempt < 50 gp, cap 5 m/item) — `backend/config.py` and mirrored in `profit.js`.
- Buy limits cap real profit: `count` column = max crafts per 4 h, `net_4h` in row detail.
- Volume gate (5 m trade volume of the scarcest ingredient) hides illiquid "ghost profits".
- Price staleness: `/latest` values older than 15 min fall back to the 5 m then 1 h window
  averages (marked ≈).
