"""Async database engine, session factory and lifecycle.

SQLite: WAL mode + busy_timeout set on every connection.
PostgreSQL: pool_size=10 via asyncpg.
init_db: runs `alembic upgrade head` when AUTO_MIGRATE=1, else create_all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeMeta

from app.config import settings
from app.models import Base

logger = structlog.get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _make_engine() -> AsyncEngine:
    kwargs: dict[str, Any] = {"echo": False, "pool_pre_ping": True}
    if settings.is_postgres:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    engine = create_async_engine(settings.DATABASE_URL, **kwargs)
    if settings.is_sqlite:
        _attach_sqlite_pragmas(engine)
    return engine


def _attach_sqlite_pragmas(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_conn: Any, _record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


engine: AsyncEngine = _make_engine()
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def _run_alembic_upgrade() -> None:
    import asyncio

    from alembic import command
    from alembic.config import Config

    def _upgrade() -> None:
        cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
        cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        command.upgrade(cfg, "head")

    await asyncio.to_thread(_upgrade)


async def init_db() -> None:
    if settings.AUTO_MIGRATE:
        try:
            await _run_alembic_upgrade()
            logger.info("db.init.alembic_upgraded")
            return
        except Exception:
            logger.exception("db.init.alembic_failed_fallback_create_all")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn))
    logger.info("db.init.create_all_done")


__all__ = ["engine", "AsyncSessionLocal", "get_db", "init_db", "Base", "DeclarativeMeta"]
