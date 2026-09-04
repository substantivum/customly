"""OpenDota API client: Dota 2 account lookup + rank medal.

Mirrors `bot.services.henrik` in shape. Keyed on the player's *friend id* (the
in-game Friend ID, which is the account id / SteamID32). The free tier needs no
key; `OPENDOTA_API_KEY` only raises the rate limit.

OpenDota returns rank as a `rank_tier` integer — tens digit is the medal
(1 Herald … 8 Immortal), ones digit is the star (1-5). `dota_rank_name` turns
that into something a player recognises.

Docs: https://docs.opendota.com
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

from bot.config import settings

log = logging.getLogger("customly.opendota")

BASE = "https://api.opendota.com/api"
TIMEOUT = 8.0
RETRY_BACKOFF = (0.5, 1.5)

_MEDALS = {
    1: "Herald", 2: "Guardian", 3: "Crusader", 4: "Archon",
    5: "Legend", 6: "Ancient", 7: "Divine", 8: "Immortal",
}

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


class DotaError(Exception):
    """Base for every way an OpenDota call can fail to produce data."""


class AccountNotFound(DotaError):
    pass


class RateLimited(DotaError):
    pass


class DotaTimeout(DotaError):
    pass


class DotaUnavailable(DotaError):
    pass


@dataclass
class DotaPlayer:
    account_id: int
    persona: str | None
    rank_tier: int | None
    leaderboard_rank: int | None


def parse_player(payload: dict) -> DotaPlayer:
    profile = payload.get("profile") or {}
    return DotaPlayer(
        account_id=profile.get("account_id", 0),
        persona=profile.get("personaname"),
        rank_tier=payload.get("rank_tier"),
        leaderboard_rank=payload.get("leaderboard_rank"),
    )


def dota_rank_name(rank_tier: int | None, leaderboard_rank: int | None = None) -> str | None:
    """A rank_tier like 54 -> 'Legend 4'; 80 -> 'Immortal'. None if unranked."""
    if not rank_tier:
        return None
    medal, star = rank_tier // 10, rank_tier % 10
    name = _MEDALS.get(medal)
    if not name:
        return None
    if medal == 8:
        return f"Immortal #{leaderboard_rank}" if leaderboard_rank else "Immortal"
    return f"{name} {star}" if star else name


def _params() -> dict:
    return {"api_key": settings.opendota_api_key} if settings.opendota_api_key else {}


async def _get_once(url: str) -> dict:
    log.debug("GET %s", url)
    try:
        async with _get_session().get(
            url, params=_params(), timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as resp:
            if resp.status == 404:
                log.info("404 %s", url)
                raise AccountNotFound(url)
            if resp.status == 429:
                log.warning("rate limited: %s", url)
                raise RateLimited()
            if resp.status != 200:
                log.warning("HTTP %s: %s", resp.status, url)
                raise DotaUnavailable(f"HTTP {resp.status}")
            return await resp.json()
    except asyncio.TimeoutError as e:
        log.warning("timeout: %s", url)
        raise DotaTimeout() from e
    except aiohttp.ClientError as e:
        log.warning("client error on %s: %s", url, e)
        raise DotaUnavailable(str(e)) from e


async def _get(url: str) -> dict:
    delays = (*RETRY_BACKOFF, None)
    for i, delay in enumerate(delays):
        try:
            return await _get_once(url)
        except (RateLimited, DotaTimeout):
            if i == len(delays) - 1:
                raise
            await asyncio.sleep(delay)


async def fetch_player(account_id: int) -> DotaPlayer:
    """Look a Dota account up by friend id (= account id). Raises AccountNotFound
    when OpenDota has no public profile for it (private, or never synced)."""
    payload = await _get(f"{BASE}/players/{account_id}")
    player = parse_player(payload)
    # OpenDota answers 200 with an empty profile for accounts it has never seen;
    # without a profile there's nothing to verify, so treat it as not-found.
    if not player.persona and not player.account_id:
        raise AccountNotFound(str(account_id))
    log.info("resolved dota %s -> persona=%s rank_tier=%s",
             account_id, player.persona, player.rank_tier)
    return player
