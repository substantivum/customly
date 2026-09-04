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


# ------------------------------------------------------------- unlinking ---
# One place that knows how to wipe each identity, shared by the player's own
# /unlink and the admin's /admin unlink so the two can never drift apart.
IDENTITIES = ("valorant", "cs2", "dota2", "steam")


def clear_identity(u, what: str) -> bool:
    """Wipe one identity (or "all") off a User row in place. Returns whether
    anything was actually linked to clear; the caller commits."""
    if what == "all":
        return any([clear_identity(u, w) for w in IDENTITIES])
    if what == "valorant":
        if not u.riot_id:
            return False
        u.riot_id = u.riot_puuid = u.riot_region = None
        u.riot_status = u.riot_reviewed_by = u.riot_reviewed_at = None
        u.cur_rank = u.cur_rr = u.peak_rank = u.rank_updated_at = None
        return True
    if what == "cs2":
        if not u.cs2_nick:
            return False
        u.cs2_nick = u.cs2_faceit_id = None
        u.cs2_status = u.cs2_reviewed_by = u.cs2_reviewed_at = None
        u.cs2_level = u.cs2_elo = u.cs2_updated_at = None
        return True
    if what == "dota2":
        if not u.dota_friend_id:
            return False
        u.dota_friend_id = None
        u.dota_status = u.dota_reviewed_by = u.dota_reviewed_at = None
        u.dota_rank_tier = u.dota_leaderboard = u.dota_updated_at = None
        return True
    if what == "steam":
        if not u.steam_id:
            return False
        u.steam_id = None
        return True
    return False
