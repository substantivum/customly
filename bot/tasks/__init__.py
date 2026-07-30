"""APScheduler jobs (reminders, ready-check timeouts, season rollover).

Stubbed: wire concrete jobs here. The scheduler is started in __main__.
"""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def start() -> None:
    if not scheduler.running:
        scheduler.start()
