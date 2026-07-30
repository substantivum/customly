"""Async SQLAlchemy engine + session factory. SQLite tuned with WAL."""
from __future__ import annotations

import os

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings
from bot.db.models import Base

# Ensure the data dir exists (sqlite file lives on the mounted volume)
_db_dir = os.path.dirname(settings.db_path)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

engine = create_async_engine(settings.db_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


async def init_db() -> None:
    """Create tables on first boot. (Use Alembic in production.)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # ensure pragmas applied on this connection too
        await conn.execute(text("PRAGMA journal_mode=WAL"))
