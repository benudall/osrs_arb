# OSRS Crafting Arb Tool — Plan

Buy materials off GE → craft → sell product. Find profitable recipes for player's skill levels.
Stack: Python (FastAPI) backend, React (Vite + TS) frontend.

---

## 1. Data sources

Real-time Prices API (`https://prices.runescape.wiki/api/v1/osrs`) — confirmed live.
**Must send descriptive User-Agent** (e.g. `osrs_arb - contact`). Respect ~1 req/sec.

| Endpoint | Use |
|---|---|
| `/mapping` | item id → name, members flag, **GE buy limit**, highalch. One-time fetch into SQLite `items` table (rarely changes) |
| `/latest` | current instant-buy/high + instant-sell/low per item. Primary price source |
| `/5m`, `/1h` | averaged prices + `highPriceVolume`/`lowPriceVolume`. Volume filter + fallback when latest is stale |
| `/timeseries?itemId=&timestep=5m\|1h\|6h\|24h` | optional later: trend/sparkline, volatility |

Price semantics (convention): `high` = price buyers pay (you buy materials at `high`). `low` = price sellers get (you sell product at `low`).
`highTime`/`lowTime` → staleness check; fall back to `/1h` avg if latest older than ~15 min.

**Recipe data — no official API.** Build curated recipe DB in repo (`backend/data/recipes.json`), seeded from wiki calculator pages per skill. Item IDs resolved against `/mapping`. One-time seeding script + manual review. Recipe record:

```json
{
  "id": "iron_knife",
  "skill": "smithing", "level": 30,
  "members": false,
  "materials": [{"item_id": 2351, "qty": 1}],          // iron bar
  "product":   {"item_id": 2, "qty": 1},               // actually knife id differs; example only
  "actions_per_input": 1
}
```

Supports multi-material recipes, batch yields (e.g. bolt tips x N, dart tips x N), and alternative recipes (e.g. gold bar w/ gauntlets → keep as separate recipe ids).

## 2. Backend — Python / FastAPI

```
backend/
  app/
    main.py            # FastAPI app, CORS for Vite dev
    config.py          # UA string, TTLs, tax rate, volume floor
    providers/
      wiki_api.py      # httpx client: mapping / latest / 5m / 1h, UA header, rate limit, retries
    db/
      sqlite.py        # stdlib sqlite3, WAL mode, schema init/migrations, thread-local conn
      dao.py           # queries: upsert items/prices, load recipes, latest-price lookup
    core/
      prices.py        # normalize: best price per item (latest w/ staleness fallback)
      profit.py        # pure calc: cost, gross, net, tax, limits
      recipes.py       # validate recipes.json, seed into DB, index by skill
    api/
      routes.py        # GET /api/skills, /api/recipes?levels=...&mode=...&f2p=...
    schemas.py         # pydantic response models
  data/recipes.json
  scripts/seed_recipes.py
  tests/                # profit math unit tests (tax edge cases, staleness fallback)
  var/osrs_arb.sqlite   # gitignored — single DB file
```

### SQLite schema

Stdlib `sqlite3` (no ORM), WAL mode, `var/` gitignored. `recipes.json` stays source-of-truth in repo (reviewable diffs); seed script loads it into DB.

```sql
CREATE TABLE items (
  id INTEGER PRIMARY KEY,             -- wiki item id
  name TEXT NOT NULL,
  members INTEGER NOT NULL,
  buy_limit INTEGER,
  highalch INTEGER,
  updated_at TEXT NOT NULL
);
CREATE TABLE price_snapshots (
  item_id INTEGER NOT NULL REFERENCES items(id),
  ts INTEGER NOT NULL,                -- unix, from highTime/lowTime or fetch time
  high INTEGER, low INTEGER,          -- null = no data this window
  high_vol INTEGER, low_vol INTEGER,  -- from /5m
  source TEXT NOT NULL,               -- 'latest' | '5m' | '1h'
  PRIMARY KEY (item_id, ts, source)
);
CREATE TABLE recipes (
  id TEXT PRIMARY KEY,
  skill TEXT NOT NULL, level INTEGER NOT NULL,
  members INTEGER NOT NULL,
  product_item_id INTEGER NOT NULL, product_qty INTEGER NOT NULL,
  materials_json TEXT NOT NULL,       -- [{item_id, qty}] — curated data, no join table needed
  UNIQUE (skill, id)
);
CREATE TABLE players (               -- hiscores cache (~5 min TTL)
  name TEXT PRIMARY KEY,
  skills_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);
```

Hot path (recipe scan) reads latest price per item — keep small in-mem dict warmed from DB + refreshed by background task; DB is durability + history, not per-request query surface.

Refresh loop: background task re-pulls `/latest` + `/5m` every ~60s (within rate limit), upserts `price_snapshots`. Mapping upserted every 24h. Old snapshots pruned (e.g. keep 7d of 5m, downsample older later).

### Profit math

```
cost  = Σ material.price(high, per-unit buy) * qty
gross = product.price(low, per-unit sell) * product_qty
tax   = 2% of gross, exempt if item price ≤ 100 gp, capped 5m/item (config in one place; Jagex tweaks it)
net   = gross - tax - cost
net_per_hour ≈ net * actions_per_hour(level)   // optional phase 2; needs xp-rate table
```

Two margin modes (user toggle):
- **conservative**: buy @ `high`, sell @ `low` (instant everything)
- **optimistic**: buy @ `low`, sell @ `high` (patience / flip-style)

Row-level gates:
- `volume` = min(product lowPriceVolume, Σ material highPriceVolume) from `/5m` — hide illiquid "ghost profit"
- `buy_limit` from mapping → `max_craftable_per_4h`, `max_net_per_4h = net * min(product_qty*limit, ...)`
- staleness flag if price older than threshold

### API

- `GET /api/skills` → production skills with recipe counts (Smithing, Cooking, Crafting, Fletching, Herblore, Runecrafting, Magic, Prayer, Firemaking, Construction)
- `GET /api/recipes?skills=smithing,crafting&levels=smithing:70&mode=conservative&f2p_only=false&min_volume=500`
  → rows: `product{name,id,price,limit}`, `materials[{name,qty,price}]`, `cost`, `gross`, `net`, `net_pct`, `volume`, `buy_limit`, `members`
  Client-side sorting; server just filters.

## 3. Frontend — React + TS

```
frontend/
  src/
    App.tsx
    api/client.ts        # typed fetch wrapper
    components/
      LevelInputs.tsx    # per-skill number inputs; "fetch player" pulls hiscores (see below)
      SkillFilter.tsx    # only production skills w/ recipes, hide locked (lvl 0) unless toggled
      RecipeTable.tsx    # TanStack Table: sortable product/materials/cost/gross/net/volume/members
      ModeToggle.tsx     # conservative/optimistic, f2p-only, min-volume slider
    types.ts
```

- TanStack Table for sorting; material cell renders `2x Iron bar (250gp)` style.
- Columns: product | materials | cost | gross | net | net% | volume | count (buy-limit based 4h cap) | f2p/member.
- Default sort: net desc. Row click → expandable detail (per-material breakdown, tax, limit math).
- Color: green/red net. Sticky header. Debounced refetch (30s) w/ manual refresh button.

### Player skill input
Phase 1: manual entry + localStorage persistence. Only show production-skill inputs (hiscores API has ~all skills; only show ones the recipe DB covers).
Phase 2 (optional): hiscores lookup — `https://services.runescape.com/m=hiscore_oldschool/index_lite.json?player=NAME` (CORS-blocked → proxy through FastAPI). Fills inputs, overridable per user's spec.

## 4. Milestones

1. **M1 — data spine**: sqlite schema init + dao; wiki_api client + UA + refresh loop writing snapshots; profit math module + unit tests. CLI sanity: `python -m scripts.best_flips` prints top nets to console.
2. **M2 — recipes**: seed 3 skills first (Smithing, Cooking, Crafting — best f2p coverage), schema validation, `GET /api/recipes` live.
3. **M3 — React table**: levels input, filters, sortable table, modes.
4. **M4 — remaining skills** (Fletching, Herblore, Runecrafting, Magic, Prayer, Firemaking), batch-yield recipes.
5. **M5 — polish**: hiscores proxy, timeseries sparkline, net/hour via xp rates, watchlist.

## 5. Risks / notes

- **Recipe DB is the real work** — API gives prices free; recipes are hand-curated. Keep schema simple, review via diff.
- Volume gating essential: /latest alone yields fake margins on 2-trade items.
- GE tax + buy limits materially change real profit; show both net and net-per-4h.
- Price volatility: 5m window noisy; conservative mode + staleness flags mitigate.
- Hiscores JSON endpoint is unofficial-ish; proxy server-side, cache player results ~5 min.
- Rate limit: single background refresher, never per-request fetches.
- SQLite is plenty: single-process, low write volume (1 snapshot batch/min). If history grows big, downsample instead of switching DB.
