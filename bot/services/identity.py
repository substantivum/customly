"""Riot identity: tag string only, no API, no RSO."""
from __future__ import annotations

import re

from bot.core.errors import BotError

TAG_RE = re.compile(r"^.{3,16}#[A-Za-z0-9]{3,5}$")


def normalize_tag(raw: str) -> str:
    s = raw.strip()
    if not TAG_RE.match(s):
        raise BotError("Riot ID must look like `TenZ#NA1` (Name#TAG).")
    return s
