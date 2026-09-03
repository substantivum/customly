"""Guards for the translation catalogs.

These are cheap, static checks — no bot, no database — but they catch the two
ways localization actually breaks in practice: a key that exists in one language
and not the other, and a placeholder that a translator quietly dropped (which
turns into a `KeyError` at render time, in front of players).

The last two tests walk the source tree instead of the catalogs, so a `t("…")`
added to a new screen can't ship without its string.
"""
from __future__ import annotations

import ast
import pathlib
import string

import pytest

from bot.i18n import DEFAULT_LANG, lang_context, t
from bot.i18n.catalog import CATALOGS

BOT_DIR = pathlib.Path(__file__).resolve().parent.parent / "bot"
EN = CATALOGS[DEFAULT_LANG]
OTHER_LANGS = [k for k in CATALOGS if k != DEFAULT_LANG]


def placeholders(template: str) -> set[str]:
    """The named `{fields}` a template expects."""
    return {
        name for _, name, _, _ in string.Formatter().parse(template) if name
    }


@pytest.mark.parametrize("lang", OTHER_LANGS)
def test_every_language_has_the_same_keys(lang):
    other = CATALOGS[lang]
    assert set(other) == set(EN), (
        f"missing in {lang}: {sorted(set(EN) - set(other))}; "
        f"extra in {lang}: {sorted(set(other) - set(EN))}"
    )


@pytest.mark.parametrize("lang", OTHER_LANGS)
def test_placeholders_match_english(lang):
    bad = {
        key: (placeholders(EN[key]), placeholders(value))
        for key, value in CATALOGS[lang].items()
        if key in EN and placeholders(EN[key]) != placeholders(value)
    }
    assert not bad, f"placeholder mismatch in {lang}: {bad}"


@pytest.mark.parametrize("lang", list(CATALOGS))
def test_no_string_is_empty(lang):
    empty = [k for k, v in CATALOGS[lang].items() if not v.strip()]
    assert not empty, f"empty strings in {lang}: {empty}"


@pytest.mark.parametrize("lang", list(CATALOGS))
def test_command_metadata_fits_discords_limit(lang):
    """Discord rejects a command/parameter description over 100 characters, and
    it rejects the whole command tree with it — so this is a hard failure."""
    too_long = {
        k: len(v) for k, v in CATALOGS[lang].items()
        if k.startswith("cmd.") and len(v) > 100
    }
    assert not too_long, f"over 100 chars in {lang}: {too_long}"


# --------------------------------------------------------------- lookup ------
def test_missing_key_returns_the_key_rather_than_raising():
    assert t("no.such.key.anywhere") == "no.such.key.anywhere"


def test_untranslated_key_falls_back_to_english():
    with lang_context("ru"):
        assert t("veto.action.ban") == CATALOGS["ru"]["veto.action.ban"]
    # A language we don't ship at all degrades to English rather than blowing up.
    with lang_context("de"):
        assert t("veto.action.ban") == EN["veto.action.ban"]


def test_bad_placeholders_do_not_raise():
    """A caller that forgets an argument gets the raw template, not a KeyError
    in the middle of answering an interaction."""
    assert "{custom_id}" in t("custom.left")


# ------------------------------------------------------ source-tree checks ---
def _literal_keys_used() -> dict[str, list[str]]:
    """Every `t("literal")` in bot/, mapped to the files that use it.

    Computed keys (`t(f"state.{s}")`) are skipped — the parametrized prefix
    tests below cover those families instead.
    """
    used: dict[str, list[str]] = {}
    for path in BOT_DIR.rglob("*.py"):
        if "catalog" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in ("t", "L")
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                used.setdefault(node.args[0].value, []).append(path.name)
    return used


def test_every_key_used_in_the_code_exists():
    unknown = {k: v for k, v in _literal_keys_used().items() if k not in EN}
    assert not unknown, f"used but not in the English catalog: {unknown}"


@pytest.mark.parametrize("prefix,values", [
    ("state", ["registration", "full", "ready", "veto", "live", "done"]),
    ("role", ["player", "admin", "superadmin"]),
    ("rank", ["player", "admin", "superadmin"]),
    ("tier", ["player", "admin", "superadmin"]),
    ("coin", ["heads", "tails"]),
    ("veto", ["attack", "defence"]),
    ("veto.action", ["ban", "pick"]),
    ("veto.side", ["t", "ct"]),
    ("btn.side", ["t", "ct"]),
    ("game", ["valorant", "dota2", "cs2"]),
    ("lang.name", list(CATALOGS)),
    ("profile.role", ["duelist", "controller", "initiator", "sentinel", "flex"]),
])
def test_computed_key_families_are_complete(prefix, values):
    """Keys the code builds at runtime (`t(f"state.{c.state}")`) have no literal
    to check, so the families are asserted whole."""
    missing = [f"{prefix}.{v}" for v in values if f"{prefix}.{v}" not in EN]
    assert not missing, f"missing catalog keys: {missing}"
