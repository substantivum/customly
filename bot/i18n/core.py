"""Message catalog lookup.

Every user-facing string in the bot comes from here. `t()` reads the language
from a `ContextVar` that is bound once per interaction (see `bot.i18n.ui`), so
nothing in the call chain below an interaction handler needs to carry a `lang`
argument around.

A missing key or a broken placeholder is logged and degrades to English (then to
the key itself) rather than raising: a translation gap must never be able to
break a match flow.
"""
from __future__ import annotations

import contextlib
import logging
from contextvars import ContextVar, Token

from bot.i18n.catalog import CATALOGS

log = logging.getLogger("customly.i18n")

DEFAULT_LANG = "en"
LANGS: tuple[str, ...] = tuple(CATALOGS)

# Human names for the languages, in the language itself — a picker is easier to
# use when every option is legible to the person who needs it.
LANG_NAME = {"en": "English", "ru": "Русский"}

_lang: ContextVar[str] = ContextVar("customly_lang", default=DEFAULT_LANG)


def normalize(lang: str | None) -> str:
    """Any stored/URL/locale-ish value → a language we actually ship."""
    if not lang:
        return DEFAULT_LANG
    lang = lang.strip().lower().replace("_", "-").split("-")[0]
    return lang if lang in CATALOGS else DEFAULT_LANG


def current_lang() -> str:
    return _lang.get()


def set_current_lang(lang: str | None) -> Token:
    return _lang.set(normalize(lang))


def reset_lang(token: Token) -> None:
    _lang.reset(token)


@contextlib.contextmanager
def lang_context(lang: str | None):
    """Bind a language for the duration of a block (sync or async body)."""
    token = set_current_lang(lang)
    try:
        yield normalize(lang)
    finally:
        _lang.reset(token)


@contextlib.asynccontextmanager
async def use_lang(guild_id: int | None):
    """Bind the guild's language around work that isn't driven by an interaction.

    Background jobs (board redraws, per-turn timers) run in their own tasks and
    must not inherit whichever language the click that scheduled them happened to
    be in — a board belongs to its guild, not to the last person who touched it.
    """
    from bot.services import guild_svc

    lang = await guild_svc.get_lang(guild_id)
    token = set_current_lang(lang)
    try:
        yield lang
    finally:
        _lang.reset(token)


def lookup(lang: str, key: str) -> str | None:
    """Raw template for a key in one language, without fallback."""
    return CATALOGS.get(normalize(lang), {}).get(key)


def t(key: str, /, **kwargs) -> str:
    """The string for `key` in the currently bound language."""
    lang = _lang.get()
    template = CATALOGS.get(lang, {}).get(key)
    if template is None:
        template = CATALOGS[DEFAULT_LANG].get(key)
        if template is None:
            log.warning("missing i18n key: %r", key)
            return key
        if lang != DEFAULT_LANG:
            log.warning("untranslated i18n key %r for %r", key, lang)
    if not kwargs:
        # A template with a literal brace (an example, a code snippet) and no
        # arguments to fill is not a formatting error — only call .format()
        # when there's actually something to substitute.
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError) as e:
        log.warning("bad placeholders for i18n key %r (%s): %s", key, lang, e)
        return template
