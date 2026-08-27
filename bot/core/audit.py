"""Append-only audit logging."""
from __future__ import annotations

import json

from bot.db import SessionLocal
from bot.db.models import AuditLog


async def log(
    guild_id: int,
    actor_id: int | None,
    action: str,
    target: str | None = None,
    **meta,
) -> None:
    async with SessionLocal() as s:
        s.add(
            AuditLog(
                guild_id=guild_id,
                actor_id=actor_id,
                action=action,
                target=target,
                meta_json=json.dumps(meta) if meta else None,
            )
        )
        await s.commit()
