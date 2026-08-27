"""Riot identity: tag string only, no API, no RSO."""
from __future__ import annotations

import re

from bot.core.errors import BotError
from bot.i18n import t

TAG_RE = re.compile(r"^.{3,16}#[A-Za-z0-9]{3,5}$")


def normalize_tag(raw: str) -> str:
    s = raw.strip()
    if not TAG_RE.match(s):
        raise BotError(t("error.riot_id"))
    return s
