"""Queue helpers. The custom's queue is the source of truth; this module
answers 'is it full?' and returns members in join order."""
from __future__ import annotations

from sqlalchemy import select

from bot.db import SessionLocal
from bot.db.models import Queue, QueueMember


async def queue_for_custom(custom_id: int):
    async with SessionLocal() as s:
        return (
            await s.execute(select(Queue).where(Queue.custom_id == custom_id))
        ).scalar_one_or_none()


async def members(queue_id: int) -> list[int]:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(QueueMember.user_id)
            .where(QueueMember.queue_id == queue_id)
            .order_by(QueueMember.joined_at)
        )
        return [r[0] for r in rows.all()]


async def is_full(custom_id: int) -> bool:
    q = await queue_for_custom(custom_id)
    if not q:
        return False
    return len(await members(q.queue_id)) >= q.size
