"""Per-guild settings, stored as JSON on the `guilds` row.

`lang` is read on nearly every render, so its resolved value is cached
in-process and invalidated on write — a board redraw must not cost a
database round trip per string. `notify_role` is read once per custom
creation and isn't cached.
"""
from __future__ import annotations

import json
import logging

from bot.db import SessionLocal
from bot.db.models import Guild
from bot.i18n import DEFAULT_LANG, LANGS, normalize

log = logging.getLogger("customly.guild")

_lang_cache: dict[int, str] = {}


def _settings(guild: Guild | None) -> dict:
    if not guild or not guild.settings_json:
        return {}
    try:
        data = json.loads(guild.settings_json)
    except json.JSONDecodeError:
        log.warning("guild %s has unreadable settings_json; treating as empty",
                    getattr(guild, "guild_id", "?"))
        return {}
    return data if isinstance(data, dict) else {}


async def get_lang(guild_id: int | None) -> str:
    """The language this guild speaks. DMs and unknown guilds get the default."""
    if guild_id is None:
        return DEFAULT_LANG
    cached = _lang_cache.get(guild_id)
    if cached is not None:
        return cached
    async with SessionLocal() as s:
        g = await s.get(Guild, guild_id)
    lang = normalize(_settings(g).get("lang"))
    _lang_cache[guild_id] = lang
    return lang


async def set_lang(guild_id: int, lang: str) -> str:
    """Persist the guild's language. Returns the normalized value stored."""
    lang = normalize(lang)
    async with SessionLocal() as s:
        g = await s.get(Guild, guild_id)
        if g is None:
            g = Guild(guild_id=guild_id, settings_json="{}")
            s.add(g)
        data = _settings(g)
        data["lang"] = lang
        g.settings_json = json.dumps(data)
        await s.commit()
    _lang_cache[guild_id] = lang
    return lang


async def get_notify_role(guild_id: int | None) -> int | None:
    """The role to ping when a custom opens for registration, if configured."""
    if guild_id is None:
        return None
    async with SessionLocal() as s:
        g = await s.get(Guild, guild_id)
    return _settings(g).get("notify_role")


async def set_notify_role(guild_id: int, role_id: int | None) -> None:
    """Persist the guild's notify role. `role_id=None` clears it."""
    async with SessionLocal() as s:
        g = await s.get(Guild, guild_id)
        if g is None:
            g = Guild(guild_id=guild_id, settings_json="{}")
            s.add(g)
        data = _settings(g)
        if role_id is None:
            data.pop("notify_role", None)
        else:
            data["notify_role"] = role_id
        g.settings_json = json.dumps(data)
        await s.commit()


def forget(guild_id: int | None = None) -> None:
    """Drop cached languages — for tests, and for a guild the bot has left."""
    if guild_id is None:
        _lang_cache.clear()
    else:
        _lang_cache.pop(guild_id, None)


def available() -> tuple[str, ...]:
    return LANGS
