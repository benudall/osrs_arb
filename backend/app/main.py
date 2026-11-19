import asyncio
import contextlib
import logging
import pathlib

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .core import prices as prices_mod
from .core import recipes as recipes_mod
from .db import dao
from .db.sqlite import Database
from .api.routes import router
from .providers.wiki_api import WikiAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("osrs_arb")

WEB_DIR = pathlib.Path(__file__).resolve().parent / "web" / "static"


async def refresh_mapping(app):
    mapping = await app.state.api.mapping()
    dao.replace_items(app.state.db, mapping)
    log.info("mapping refreshed: %d items", len(mapping))


def reseed(app):
    report = recipes_mod.seed(app.state.db, config.RECIPES_PATH)
    log.info(
        "recipes seeded: %d/%d (unknown items: %s, structural errors: %d)",
        report["seeded"], report["total_in_file"], report["unknown_items"], report["skipped_structural"],
    )
    return report


async def refresh_loop(app):
    api = app.state.api
    db = app.state.db
    store = app.state.store
    while True:
        try:
            if dao.items_stale(db, config.MAPPING_TTL_SECS):
                await refresh_mapping(app)
                reseed(app)
            latest = await api.latest()
            store.update_latest(latest)
            five = await api.five_min()
            store.update_window(five, "5m")
            one = await api.one_hour()
            store.update_window(one, "1h")

            rows = []
            for item_id, d in latest.get("data", {}).items():
                rows.append((int(item_id), int(d.get("highTime") or 0), d.get("high"), d.get("low"), None, None, "latest"))
            for item_id, d in five.get("data", {}).items():
                rows.append((int(item_id), int(d.get("timestamp") or 0), d.get("avgHighPrice"), d.get("avgLowPrice"),
                             d.get("highPriceVolume"), d.get("lowPriceVolume"), "5m"))
            dao.insert_snapshots(db, rows)
            store.mark_refreshed()
            log.info("refresh ok: %d latest, %d 5m, %d 1h", len(latest.get("data", {})),
                     len(five.get("data", {})), len(one.get("data", {})))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("refresh failed; retrying next cycle")
        await asyncio.sleep(config.REFRESH_SECS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    app.state.db = Database(config.DB_PATH)
    app.state.api = WikiAPI()
    app.state.store = prices_mod.PriceStore()
    app.state.reseed = lambda db: reseed(app)

    try:
        await refresh_mapping(app)
    except Exception:  # noqa: BLE001
        log.warning("initial mapping fetch failed; using cached items table", exc_info=True)
        if not dao.get_item_map(app.state.db):
            raise
    reseed(app)

    task = asyncio.create_task(refresh_loop(app))
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await app.state.api.close()


app = FastAPI(title="OSRS Crafting Arb", lifespan=lifespan)
app.include_router(router)
# serve the vanilla JS UI (and everything else unmatched) from the same origin
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
