"""Riot identity: tag string only, no API, no RSO."""
from __future__ import annotations

import re
from urllib.parse import quote

from bot.core.errors import BotError
from bot.i18n import t

TAG_RE = re.compile(r"^.{3,16}#[A-Za-z0-9]{3,5}$")


def normalize_tag(raw: str) -> str:
    s = raw.strip()
    if not TAG_RE.match(s):
        raise BotError(t("error.riot_id"))
    return s


# ------------------------------------------------------------- profile links --
# Turn a stored handle into a clickable profile URL for the profile card, or
# None when the handle can't be resolved (the card then shows plain text).
_STEAM64_BASE = 76561197960265728
_STEAM2_RE = re.compile(r"^STEAM_\d:([01]):(\d+)$", re.I)          # STEAM_1:0:12345
_STEAM3_RE = re.compile(r"^\[?U:1:(\d+)\]?$", re.I)                 # [U:1:24691]
_VANITY_RE = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")


def steam_url(raw: str | None) -> str | None:
    """A pasted URL, a SteamID64, a vanity name, or a SteamID2/3 → profile URL."""
    s = (raw or "").strip()
    if not s:
        return None
    if re.match(r"^https?://", s, re.I):
        return s
    if re.fullmatch(r"\d{17}", s):
        return f"https://steamcommunity.com/profiles/{s}"
    if m := _STEAM2_RE.match(s):
        return f"https://steamcommunity.com/profiles/{int(m[2]) * 2 + int(m[1]) + _STEAM64_BASE}"
    if m := _STEAM3_RE.match(s):
        return f"https://steamcommunity.com/profiles/{int(m[1]) + _STEAM64_BASE}"
    if _VANITY_RE.match(s):
        return f"https://steamcommunity.com/id/{s}"
    return None


def faceit_url(nick: str) -> str:
    return f"https://www.faceit.com/en/players/{quote(nick, safe='')}"


def opendota_url(friend_id: str | None) -> str | None:
    s = (friend_id or "").strip()
    return f"https://www.opendota.com/players/{s}" if s.isdigit() else None
