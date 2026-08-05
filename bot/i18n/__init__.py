"""Localization: one catalog per language, one `t()` to reach it."""
from __future__ import annotations

from bot.i18n.core import (
    DEFAULT_LANG,
    LANG_NAME,
    LANGS,
    current_lang,
    lang_context,
    lookup,
    normalize,
    set_current_lang,
    t,
    use_lang,
)

__all__ = [
    "DEFAULT_LANG",
    "LANGS",
    "LANG_NAME",
    "current_lang",
    "lang_context",
    "lookup",
    "normalize",
    "set_current_lang",
    "t",
    "use_lang",
]
