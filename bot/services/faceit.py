"""Faceit Data API client: CS2 player lookup + skill level / elo.

The shape of this module deliberately mirrors `bot.services.henrik` (same error
types, same retry-on-transient behaviour) so the CS2 rank flow reads the same as
the Valorant one. Unlike Henrik, Faceit **requires** an API key — an
unauthenticated call is rejected — so a missing key raises `FaceitNotConfigured`
rather than silently degrading.

Docs: https://docs.faceit.com/docs (Data API v4).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

from bot.config import settings

log = logging.getLogger("customly.faceit")

BASE = "https://open.faceit.com/data/v4"
TIMEOUT = 8.0
RETRY_BACKOFF = (0.5, 1.5)
# Which game key carries the CS2 stats in a player's `games` map.
GAME_KEY = "cs2"

_session: aiohttp.ClientSession | None = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def close() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()
    _session = None


class FaceitError(Exception):
    """Base for every way a Faceit call can fail to produce data."""


class FaceitNotConfigured(FaceitError):
    """FACEIT_API_KEY is unset — the CS2 rank flow can't run at all."""


class AccountNotFound(FaceitError):
    pass


class RateLimited(FaceitError):
    pass


class FaceitTimeout(FaceitError):
    pass


class FaceitUnavailable(FaceitError):
    pass


@dataclass
class FaceitPlayer:
    player_id: str
    nickname: str
    level: int | None
    elo: int | None


def parse_player(payload: dict) -> FaceitPlayer:
    cs2 = (payload.get("games") or {}).get(GAME_KEY) or {}
    return FaceitPlayer(
        player_id=payload.get("player_id", ""),
        nickname=payload.get("nickname", ""),
        level=cs2.get("skill_level"),
        elo=cs2.get("faceit_elo"),
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.faceit_api_key}"}


async def _get_once(url: str, params: dict | None = None) -> dict:
    log.debug("GET %s params=%s", url, params)
    try:
        async with _get_session().get(
            url, headers=_headers(), params=params,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT),
        ) as resp:
            if resp.status == 404:
                log.info("404 %s", url)
                raise AccountNotFound(url)
            if resp.status == 429:
                log.warning("rate limited: %s", url)
                raise RateLimited()
            if resp.status in (401, 403):
                log.warning("auth error %s: %s", resp.status, url)
                raise FaceitNotConfigured(f"HTTP {resp.status}")
            if resp.status != 200:
                log.warning("HTTP %s: %s", resp.status, url)
                raise FaceitUnavailable(f"HTTP {resp.status}")
            return await resp.json()
    except asyncio.TimeoutError as e:
        log.warning("timeout: %s", url)
        raise FaceitTimeout() from e
    except aiohttp.ClientError as e:
        log.warning("client error on %s: %s", url, e)
        raise FaceitUnavailable(str(e)) from e


async def _get(url: str, params: dict | None = None) -> dict:
    if not settings.faceit_api_key:
        raise FaceitNotConfigured()
    delays = (*RETRY_BACKOFF, None)
    for i, delay in enumerate(delays):
        try:
            return await _get_once(url, params)
        except (RateLimited, FaceitTimeout):
            if i == len(delays) - 1:
                raise
            await asyncio.sleep(delay)


async def fetch_player(nickname: str) -> FaceitPlayer:
    """Resolve a Faceit nickname to its player id + CS2 level/elo."""
    payload = await _get(f"{BASE}/players", params={"nickname": nickname, "game": GAME_KEY})
    player = parse_player(payload)
    log.info("resolved faceit %s -> id=%s level=%s elo=%s",
             nickname, player.player_id, player.level, player.elo)
    return player


async def fetch_player_by_id(player_id: str) -> FaceitPlayer:
    """Refresh CS2 stats keyed on the stable player id (nicknames can change)."""
    payload = await _get(f"{BASE}/players/{player_id}")
    return parse_player(payload)
