"""Per-game differences in the custom flow: which formats apply, whether a map
veto happens at all, whether the veto ends in a side choice, and what the
lobby's connect info is called.

Everything else (registration, captains, team draft) is identical across
games — this module is intentionally small.
"""
from __future__ import annotations

from bot.i18n import t

GAMES = ("valorant", "dota2", "cs2")

# Dota 2 has no map pool / veto step at all — the match goes straight from the
# draft to live. CS2 keeps the veto but only in BO1 (see FORMATS below).
HAS_VETO = {"valorant": True, "dota2": False, "cs2": True}

# CS2's side is decided by a knife round in-game, not by either captain — so
# its veto ends at the decider map with no side-choice step at all.
HAS_SIDE_CHOICE = {"valorant": True, "cs2": False}

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

# What the lobby's "how to connect" field is called. Valorant/Dota 2 share a
# party/lobby code; CS2 connects by server IP instead.
_CODE_KEY_OVERRIDES: dict[str, dict[str, str]] = {
    "cs2": {
        "label": "lobby.party_code.cs2",
        "button": "btn.set_code.cs2",
        "modal_title": "modal.code.title.cs2",
        "modal_label": "modal.code.label.cs2",
        "modal_placeholder": "modal.code.ph.cs2",
        "updated": "code.updated.cs2",
        "set": "code.set.cs2",
        "announced": "code.announced.cs2",
    },
}
_CODE_DEFAULT_KEYS = {
    "label": "lobby.party_code",
    "button": "btn.set_code",
    "modal_title": "modal.code.title",
    "modal_label": "modal.code.label",
    "modal_placeholder": "modal.code.ph",
    "updated": "code.updated",
    "set": "code.set",
    "announced": "code.announced",
}


def game_label(game: str) -> str:
    key = GAME_KEY.get(game)
    return t(key) if key else game


def has_veto(game: str) -> bool:
    return HAS_VETO.get(game, True)


def has_side_choice(game: str) -> bool:
    return HAS_SIDE_CHOICE.get(game, True)


def allowed_formats(game: str) -> tuple[str, ...]:
    return FORMATS.get(game, FORMATS["valorant"])


def side_label(choice: str) -> str:
    return t("veto.attack" if choice == "attack" else "veto.defence")


def side_button_key(choice: str) -> str:
    return "btn.attack" if choice == "attack" else "btn.defence"


def code_text(kind: str, game: str, **kwargs) -> str:
    """A party-code/lobby-IP string, worded for `game`. `kind` is one of the
    keys in _CODE_DEFAULT_KEYS (label, button, modal_title, modal_label,
    modal_placeholder, updated, set, announced)."""
    key = _CODE_KEY_OVERRIDES.get(game, {}).get(kind, _CODE_DEFAULT_KEYS[kind])
    return t(key, **kwargs)
