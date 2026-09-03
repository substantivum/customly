"""Per-game differences in the custom flow: which formats apply, whether a map
veto happens at all, and what a chosen side is called.

Everything else (registration, captains, team draft) is identical across
games — this module is intentionally small.
"""
from __future__ import annotations

from bot.i18n import t

GAMES = ("valorant", "dota2", "cs2")

# Dota 2 has no map pool / veto step at all — the match goes straight from the
# draft to live. CS2 keeps the veto but only in BO1 (see FORMATS below).
HAS_VETO = {"valorant": True, "dota2": False, "cs2": True}

GAME_KEY = {
    "valorant": "game.valorant",
    "dota2": "game.dota2",
    "cs2": "game.cs2",
}

# CS2 is BO1-only by design (see plan): a veto against a small, admin-chosen
# pool rather than the official 7-map BO3/BO5 sequence. Dota 2 keeps all three
# formats — there's no veto, but the format still sets the scheduling block
# (duration_h) used for the overlap check.
FORMATS = {
    "valorant": ("BO1", "BO3", "BO5"),
    "dota2": ("BO1", "BO3", "BO5"),
    "cs2": ("BO1",),
}

# Side-choice labels on the veto's decider map. Internal side values stay
# "attack"/"defence" everywhere (data model, controllers) — only the label a
# player sees changes per game.
_SIDE_LABEL_KEY = {
    "cs2": {"attack": "veto.side.t", "defence": "veto.side.ct"},
}
_DEFAULT_SIDE_LABEL_KEY = {"attack": "veto.attack", "defence": "veto.defence"}

_BTN_LABEL_KEY = {
    "cs2": {"attack": "btn.side.t", "defence": "btn.side.ct"},
}
_DEFAULT_BTN_LABEL_KEY = {"attack": "btn.attack", "defence": "btn.defence"}


def game_label(game: str) -> str:
    key = GAME_KEY.get(game)
    return t(key) if key else game


def has_veto(game: str) -> bool:
    return HAS_VETO.get(game, True)


def allowed_formats(game: str) -> tuple[str, ...]:
    return FORMATS.get(game, FORMATS["valorant"])


def side_label(game: str, choice: str) -> str:
    key = _SIDE_LABEL_KEY.get(game, _DEFAULT_SIDE_LABEL_KEY).get(choice, choice)
    return t(key)


def side_button_key(game: str, choice: str) -> str:
    return _BTN_LABEL_KEY.get(game, _DEFAULT_BTN_LABEL_KEY)[choice]
