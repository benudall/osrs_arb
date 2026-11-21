import calendar
import json
import time

from fastapi import APIRouter, HTTPException, Query, Request

import httpx

from .. import config
from ..core import profit
from ..db import dao
from ..providers import wiki_api
from ..schemas import (
    HiscoresResponse,
    MetaResponse,
    RecipesResponse,
    SkillsResponse,
)

router = APIRouter(prefix="/api")

MODES = ("conservative", "optimistic")


@router.get("/skills", response_model=SkillsResponse)
def skills(request: Request):
    db = request.app.state.db
    rows = db.query(
        "SELECT skill, COUNT(*) AS count FROM recipes GROUP BY skill ORDER BY skill"
    )
    return SkillsResponse(skills=[{"skill": r["skill"], "count": r["count"]} for r in rows])


def _search_words(q: str | None) -> list[str]:
    """q -> list of lowercase words to require; empty list = no search."""
    if not q:
        return []
    return [w for w in q.lower().split() if w]


def _row_matches(row: dict, words: list[str]) -> bool:
    """Case-insensitive free-text match: every word must appear in the
    product name, material names, skill, or note."""
    if not words:
        return True
    parts = [row["product"]["name"], row.get("skill") or "", row.get("note") or ""]
    parts += [m["name"] for m in row.get("materials", [])]
    haystack = " ".join(parts).lower()
    return all(w in haystack for w in words)


def _parse_levels(raw: str | None) -> dict[str, int]:
    levels: dict[str, int] = {}
    if not raw:
        return levels
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise HTTPException(400, f"bad levels entry: {part!r} (expected skill:level)")
        skill, _, lvl = part.partition(":")
        try:
            level = int(lvl)
        except ValueError:
            raise HTTPException(400, f"bad level in {part!r}")
        if not (1 <= level <= 99):
            raise HTTPException(400, f"level out of range in {part!r}")
        levels[skill.strip().lower()] = level
    return levels


@router.get("/recipes", response_model=RecipesResponse)
def recipes(
    request: Request,
    skills: str | None = Query(None, description="comma-separated skill filter"),
    levels: str | None = Query(None, description="comma-separated skill:level pairs"),
    mode: str = Query("conservative"),
    f2p_only: bool = Query(False),
    min_volume: int = Query(0, ge=0),
    q: str | None = Query(None, description="free-text search; every word must match in product name, materials, skill, or note"),
):
    if mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    db = request.app.state.db
    store = request.app.state.store
    skill_filter = {s.strip().lower() for s in skills.split(",") if s.strip()} if skills else None
    level_map = _parse_levels(levels)
    search_words = _search_words(q)

    item_map = dao.get_item_map(db)
    all_recipes = dao.get_recipes(db)

    # alchemy spells need a Nature rune: its current instant-buy price
    alchemy_cost = None
    nature_id = dao.get_name_to_id(db).get("Nature rune")
    if nature_id:
        res = store.resolve(nature_id)
        if res:
            alchemy_cost = res["high"][0]

    # craft cost per unit for every craftable item that is used as a material
    # elsewhere (cheapest recipe) — lets the detail table show what a material
    # would cost to make instead of buy. Only evaluated for products that are
    # actually someone's material — the vast majority of recipes aren't.
    material_ids = {m["item_id"] for r in all_recipes for m in r["materials"]}
    craft_costs = {}
    for r in all_recipes:
        if r["product"]["item_id"] not in material_ids:
            continue
        row = profit.evaluate_recipe(r, item_map, store, mode=mode)
        if row is None or row["product"]["qty"] < 1:
            continue
        per_unit = row["cost"] / row["product"]["qty"]
        pid = r["product"]["item_id"]
        if pid not in craft_costs or per_unit < craft_costs[pid]:
            craft_costs[pid] = per_unit

    rows, skipped_no_price, skipped_filtered = [], 0, 0
    for r in all_recipes:
        if skill_filter:
            if r["skill"] not in skill_filter and not any(es["skill"] in skill_filter for es in r.get("extra_skills", [])):
                continue
        
        # Check primary level
        lvl = level_map.get(r["skill"])
        if lvl is not None and r["level"] > lvl:
            continue
        
        # Check extra skills levels
        extra_skills = r.get("extra_skills", [])
        if any(level_map.get(es["skill"], 0) < es["level"] for es in extra_skills if es["skill"] in level_map):
            continue

        if f2p_only and r["members"]:
            continue

        row = profit.evaluate_recipe(r, item_map, store, mode=mode, craft_costs=craft_costs)
        if row is None:
            skipped_no_price += 1
            continue
        if not _row_matches(row, search_words):
            skipped_filtered += 1
            continue
        if row["volume"] < min_volume:
            skipped_filtered += 1
            continue
        rows.append(row)

    return RecipesResponse(
        rows=rows,
        meta={
            "last_refresh": store.last_refresh,
            "item_count": len(item_map),
            "recipes_total": len(all_recipes),
            "skipped_no_price": skipped_no_price,
            "skipped_filtered": skipped_filtered,
            "alchemy_cost": alchemy_cost,
            "nature_rune_id": nature_id,
        },
    )


@router.get("/meta", response_model=MetaResponse)
def meta(request: Request):
    db = request.app.state.db
    store = request.app.state.store
    return MetaResponse(
        item_count=db.query_one("SELECT COUNT(*) AS c FROM items")["c"],
        recipes_total=db.query_one("SELECT COUNT(*) AS c FROM recipes")["c"],
        last_refresh=store.last_refresh,
        mode_options=list(MODES),
    )


@router.get("/hiscores", response_model=HiscoresResponse)
def hiscores(request: Request, player: str = Query(min_length=1, max_length=12)):
    """Proxy the OSRS hiscores (CORS-blocked in browsers) and return only
    skills that exist in the recipe DB. Cached ~5 min per player."""
    db = request.app.state.db
    name = player.strip()
    db_skills = dao.distinct_skills(db)
    wanted = {s.capitalize() for s in db_skills}

    cached = dao.get_player(db, name)
    if cached:
        try:
            # stored UTC: parse with timegm (mktime would apply the local offset)
            age = calendar.timegm(time.strptime(cached["fetched_at"], "%Y-%m-%dT%H:%M:%SZ"))
            skills_cached = {k.lower(): v for k, v in json.loads(cached["skills_json"]).items()}
            if time.time() - age <= config.HISCORES_TTL_SECS:
                return HiscoresResponse(player=name, skills=skills_cached, cached=True)
        except (ValueError, TypeError, AttributeError):
            pass  # corrupt cache row -> fall through and refetch

    try:
        r = httpx.get(
            config.HISCORES_URL,
            params={"player": name},
            headers={"User-Agent": config.USER_AGENT},
            timeout=15,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        raise HTTPException(502, "hiscores request failed")
    if r.status_code != 200:
        raise HTTPException(404, "player not found or hiscores unavailable")

    try:
        data = r.json()
        all_skills = {s["name"]: int(s["level"]) for s in data["skills"]}
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, "unexpected hiscores payload")

    filtered = {s.lower(): lvl for s, lvl in all_skills.items() if s in wanted}
    dao.upsert_player(db, name, json.dumps(filtered))
    return HiscoresResponse(player=name, skills=filtered, cached=False)


@router.post("/admin/reseed")
def reseed(request: Request):
    """Re-read recipes.json into the DB (used after editing recipes)."""
    db = request.app.state.db
    report = request.app.state.reseed(db)
    return report


@router.post("/admin/refresh-mapping")
async def refresh_mapping(request: Request):
    db = request.app.state.db
    mapping = await request.app.state.api.mapping()
    dao.replace_items(db, mapping)
    report = request.app.state.reseed(db)
    return {"items": len(mapping), **report}
