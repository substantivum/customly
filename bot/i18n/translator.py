"""Slash-command localization.

Discord resolves command metadata against the *viewer's own client locale*, not
against the guild's language setting — the two are independent by design, and a
Russian-client user sees Russian descriptions even in an English guild.

Command **names** stay English on purpose: they are how people (and the manual)
refer to the bot, and a name that changes per viewer can't be written down.
Descriptions, parameter descriptions and choice names are translated.
"""
from __future__ import annotations

import discord
from discord import app_commands

from bot.i18n.catalog import CATALOGS
from bot.i18n.core import DEFAULT_LANG, lookup

# Discord locales that map onto a catalog we ship.
LOCALE_LANG = {
    discord.Locale.russian: "ru",
    discord.Locale.american_english: "en",
    discord.Locale.british_english: "en",
}


def L(key: str) -> app_commands.locale_str:
    """A command string that can be translated.

    The English text is what a client with no matching locale sees, and the key
    rides along in `extras` so the translator can find the other languages.
    """
    return app_commands.locale_str(CATALOGS[DEFAULT_LANG][key], key=key)


class BotTranslator(app_commands.Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContext,
    ) -> str | None:
        key = string.extras.get("key")
        lang = LOCALE_LANG.get(locale)
        if not key or lang is None or lang == DEFAULT_LANG:
            return None
        return lookup(lang, key)
