"""HenrikDev Valorant API client: account lookup + MMR (rank) lookup.

Both endpoints work unauthenticated; sending the raw key (no "Bearer" prefix)
in `Authorization` just raises the rate-limit tier — see
https://docs.henrikdev.xyz.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

from bot.config import settings

log = logging.getLogger("valbot.henrik")

BASE = "https://api.henrikdev.xyz"
ACCOUNT_TIMEOUT = 8.0
MMR_TIMEOUT = 5.0

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


def _headers() -> dict[str, str]:
    return {"Authorization": settings.henrik_api_key} if settings.henrik_api_key else {}


class HenrikError(Exception):
    """Base for every way a HenrikDev call can fail to produce data."""


class AccountNotFound(HenrikError):
    pass


class RateLimited(HenrikError):
    pass


class HenrikTimeout(HenrikError):
    pass


class HenrikUnavailable(HenrikError):
    pass


@dataclass
class RiotAccount:
    puuid: str
    region: str
    name: str
    tag: str
    account_level: int


@dataclass
class RiotRank:
    cur_tier: str | None
    cur_rr: int | None
    peak_tier: str | None
    peak_rr: int | None


def parse_account(payload: dict) -> RiotAccount:
    d = payload.get("data") or {}
    return RiotAccount(
        puuid=d["puuid"], region=d["region"], name=d["name"], tag=d["tag"],
        account_level=d.get("account_level", 0),
    )


def parse_mmr(payload: dict) -> RiotRank:
    d = payload.get("data") or {}
    cur, peak = d.get("current") or {}, d.get("peak") or {}
    return RiotRank(
        cur_tier=(cur.get("tier") or {}).get("name"), cur_rr=cur.get("rr"),
        peak_tier=(peak.get("tier") or {}).get("name"), peak_rr=peak.get("rr"),
    )


async def _get(url: str, timeout: float) -> dict:
    log.debug("GET %s", url)
    try:
        async with _get_session().get(
            url, headers=_headers(), timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status == 404:
                log.info("404 %s", url)
                raise AccountNotFound(url)
            if resp.status == 429:
                log.warning("rate limited: %s", url)
                raise RateLimited()
            if resp.status != 200:
                log.warning("HTTP %s: %s", resp.status, url)
                raise HenrikUnavailable(f"HTTP {resp.status}")
            return await resp.json()
    except asyncio.TimeoutError as e:
        log.warning("timeout: %s", url)
        raise HenrikTimeout() from e
    except aiohttp.ClientError as e:
        log.warning("client error on %s: %s", url, e)
        raise HenrikUnavailable(str(e)) from e


async def fetch_account(name: str, tag: str) -> RiotAccount:
    payload = await _get(f"{BASE}/valorant/v1/account/{name}/{tag}", ACCOUNT_TIMEOUT)
    account = parse_account(payload)
    log.info("resolved %s#%s -> puuid=%s region=%s", name, tag, account.puuid, account.region)
    return account


async def fetch_mmr_by_puuid(region: str, puuid: str) -> RiotRank:
    """Rank lookup keyed on the account's puuid rather than its current
    name#tag — a Riot ID's tag can change, but the puuid never does, so this
    is what every *update* (post-registration) rank check should use. Same
    response shape as the name-based v3 endpoint."""
    payload = await _get(
        f"{BASE}/valorant/v3/by-puuid/mmr/{region}/pc/{puuid}", MMR_TIMEOUT
    )
    rank = parse_mmr(payload)
    log.debug("mmr %s: cur=%s peak=%s", puuid, rank.cur_tier, rank.peak_tier)
    return rank
