from pydantic import BaseModel


class SkillInfo(BaseModel):
    skill: str
    count: int


class SkillsResponse(BaseModel):
    skills: list[SkillInfo]


class MaterialRow(BaseModel):
    id: int
    name: str
    qty: int
    price: int
    stale: bool
    source: str | None
    vol: int
    sell: int | None
    sell_tax: int
    craft: int | None


class ProductRow(BaseModel):
    id: int
    name: str
    qty: int
    price: int
    buy: int | None
    value: int | None
    stale: bool
    source: str | None
    vol: int


class ToolRow(BaseModel):
    id: int | None
    name: str
    buy: int | None
    sell: int | None
    tax: int


class RecipeRow(BaseModel):
    recipe_id: str
    skill: str
    level: int
    xp: float
    members: bool
    product: ProductRow
    materials: list[MaterialRow]
    fee: int
    cost: int
    gross: int
    tax: int
    net: int
    net_pct: float | None
    volume: int
    max_crafts_4h: int
    net_4h: int | None
    mode: str
    note: str | None
    tools: list[ToolRow]
    facilities: list[str]


class RecipesMeta(BaseModel):
    last_refresh: float | None
    item_count: int
    recipes_total: int
    skipped_no_price: int
    alchemy_cost: int | None
    nature_rune_id: int | None


class RecipesResponse(BaseModel):
    rows: list[RecipeRow]
    meta: RecipesMeta


class HiscoresResponse(BaseModel):
    player: str
    skills: dict[str, int]
    cached: bool


class MetaResponse(BaseModel):
    item_count: int
    recipes_total: int
    last_refresh: float | None
    mode_options: list[str]
