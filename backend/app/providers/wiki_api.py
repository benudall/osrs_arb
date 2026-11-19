import asyncio

import httpx

from .. import config


class WikiAPI:
    """Client for the OSRS Wiki Real-time Prices API.

    Rate limits are respected by construction: only the background refresh
    loop calls this (~2 calls per REFRESH_SECS), never request handlers.
    """

    def __init__(self, base: str = config.WIKI_BASE, user_agent: str = config.USER_AGENT):
        self._client = httpx.AsyncClient(
            base_url=base,
            headers={"User-Agent": user_agent},
            timeout=httpx.Timeout(30.0),
        )

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def mapping(self) -> list:
        return await self._get("/mapping")

    async def latest(self) -> dict:
        return await self._get("/latest")

    async def five_min(self) -> dict:
        return await self._get("/5m")

    async def one_hour(self) -> dict:
        return await self._get("/1h")

    async def timeseries(self, item_id: int, timestep: str = "5m") -> dict:
        return await self._get("/timeseries", params={"itemId": item_id, "timestep": timestep})


async def fetch_mapping_once() -> list:
    """Sync-friendly helper for scripts: fetch /mapping without a server."""
    async with WikiAPI() as api:
        return await api.mapping()


def fetch_mapping_sync() -> list:
    return asyncio.run(fetch_mapping_once())
