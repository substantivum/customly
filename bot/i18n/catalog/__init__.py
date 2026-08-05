"""Message catalogs, one module per language.

English is the reference: every key must exist in `en.py`, and every other
catalog mirrors it. Adding a language means adding a module here and listing it
in `CATALOGS` — nothing else in the bot needs to change.
"""
from __future__ import annotations

from bot.i18n.catalog import en, ru

CATALOGS: dict[str, dict[str, str]] = {
    "en": en.STRINGS,
    "ru": ru.STRINGS,
}

__all__ = ["CATALOGS"]
