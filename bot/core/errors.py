"""Domain errors surfaced to users as ephemeral messages."""
from __future__ import annotations


class BotError(Exception):
    """Base; message is safe to show the user."""


class PermissionDenied(BotError):
    pass


class Blocked(BotError):
    """A guard rejected the action (e.g. occupancy guard)."""


class Conflict(BotError):
    """Scheduling overlap or similar conflict."""


class NotFound(BotError):
    pass
