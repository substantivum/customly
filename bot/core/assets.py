"""Bundled image assets — currently just map art for the match lobby.

Drop a picture per map under `bot/assets/maps/<game>/<slug>.<ext>` and the final
lobby message shows it; leave it out and the lobby degrades to the plain map
list it always had. The slug is the map name lowercased with everything but
letters and digits stripped, so `Dust II` → `dustii`, `Ascent` → `ascent`.
Accepted extensions: png, jpg, jpeg, webp (checked in that order).

Nothing here raises: a missing or unreadable asset is simply "no picture", never
a broken match flow.
"""
from __future__ import annotations

import re
from pathlib import Path

import discord

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
MAPS_DIR = ASSETS_DIR / "maps"
_EXTS = ("png", "jpg", "jpeg", "webp")


def map_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def map_image_path(game: str, map_name: str) -> Path | None:
    """The on-disk art for one map, or None if none is bundled."""
    base = MAPS_DIR / game
    for ext in _EXTS:
        p = base / f"{map_slug(map_name)}.{ext}"
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def map_image_file(game: str, map_name: str, index: int) -> tuple[discord.File, str] | None:
    """A `(File, attachment_filename)` pair for one map, or None if no art.

    The filename is deterministic from `index` + the map so a later redraw (e.g.
    when the party code is set) can rebuild the embed that points at the already
    uploaded attachment without re-sending the bytes.
    """
    p = map_image_path(game, map_name)
    if p is None:
        return None
    fname = f"map{index}_{map_slug(map_name)}{p.suffix.lower()}"
    try:
        return discord.File(p, filename=fname), fname
    except OSError:
        return None


def map_attachment_name(game: str, map_name: str, index: int) -> str | None:
    """The attachment filename a map's image was sent under, without opening it —
    for rebuilding an embed that references an attachment already on a message."""
    p = map_image_path(game, map_name)
    if p is None:
        return None
    return f"map{index}_{map_slug(map_name)}{p.suffix.lower()}"
