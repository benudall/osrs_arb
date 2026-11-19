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
):
    if mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    db = request.app.state.db
    store = request.app.state.store
    skill_filter = {s.strip().lower() for s in skills.split(",") if s.strip()} if skills else None
    level_map = _parse_levels(levels)

    item_map = dao.get_item_map(db)
    all_recipes = dao.get_recipes(db)

    # craft cost per unit for every craftable item (cheapest recipe) —
    # lets the detail table show what a material would cost to make instead of buy
    craft_costs = {}
    for r in all_recipes:
        row = profit.evaluate_recipe(r, item_map, store, mode=mode)
        if row is None or row["product"]["qty"] < 1:
            continue
        per_unit = row["cost"] / row["product"]["qty"]
        pid = r["product"]["item_id"]
        if pid not in craft_costs or per_unit < craft_costs[pid]:
            craft_costs[pid] = per_unit

    rows, skipped = [], 0
    for r in all_recipes:
        if skill_filter and r["skill"] not in skill_filter:
            continue
        lvl = level_map.get(r["skill"])
        if lvl is not None and r["level"] > lvl:
            continue
        if f2p_only and r["members"]:
            continue
        row = profit.evaluate_recipe(r, item_map, store, mode=mode, craft_costs=craft_costs)
        if row is None:
            skipped += 1
            continue
        if row["volume"] < min_volume:
            skipped += 1
            continue
        rows.append(row)

    return RecipesResponse(
        rows=rows,
        meta={
            "last_refresh": store.last_refresh,
            "item_count": len(item_map),
            "recipes_total": len(all_recipes),
            "skipped_no_price": skipped,
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
        age = time.mktime(time.strptime(cached["fetched_at"], "%Y-%m-%dT%H:%M:%SZ"))
        if time.time() - age <= config.HISCORES_TTL_SECS:
            skills_cached = {k.lower(): v for k, v in json.loads(cached["skills_json"]).items()}
            return HiscoresResponse(player=name, skills=skills_cached, cached=True)

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
