"""Channel-name slugs.

Discord lowercases and rewrites text-channel names on its side; doing it here
first means what we ask for is what we get (and what other code can look up).
Voice channels keep their case, but the same slug is used so the two families of
channels for one custom read the same in the sidebar.
"""
from __future__ import annotations


def slugify(raw: str, *, limit: int = 90, fallback: str = "custom") -> str:
    """Lowercase, hyphen-joined, only `a-z0-9-_` (plus any other alphanumerics —
    Cyrillic names survive). Returns `fallback` when nothing usable is left."""
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw.lower())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:limit] or fallback


def channel_slug(creator: str, name: str) -> str:
    """`#<creator>-<name>` for a custom's registration channel."""
    return slugify(f"{creator}-{name}")


def team_vc_name(custom_name: str, side: str, nickname: str | None) -> str:
    """`<custom>-<side>-<captain>` — e.g. `friday-5v5-a-salta`.

    The captain's nickname is what makes the channel recognisable at a glance;
    the custom's name keeps two concurrent games apart. Channels are tracked by
    id, so duplicates (same name, same captain) would be harmless.
    """
    side = side.lower()
    head = slugify(custom_name, limit=55, fallback="")
    tail = slugify(nickname or "", limit=32, fallback="")
    if not head and not tail:      # emoji-only names leave nothing to slug
        return f"team-{side}"
    return "-".join(p for p in (head, side, tail) if p)[:95]
