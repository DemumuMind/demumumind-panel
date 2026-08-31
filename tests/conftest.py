"""Test fixtures — isolated in-memory SQLite, httpx ASGI client.

Env vars are set BEFORE importing the app so the engine/settings pick up
the test database and no alembic/redis is touched.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///file:dm_test?mode=memory&cache=shared&uri=true")
os.environ.setdefault("AUTO_MIGRATE", "0")
os.environ.setdefault("PANEL_API_KEY", "test-panel-key-0123456789abcdef")
os.environ.setdefault("REDIS_URL", "")

from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import AsyncSessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.provider_manager import get_manager  # noqa: E402

PANEL_KEY = os.environ["PANEL_API_KEY"]
ADMIN_HEADERS = {"Authorization": f"Bearer {PANEL_KEY}"}


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db() -> AsyncIterator[None]:
    await init_db()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM agent_usage"))
        await conn.execute(text("DELETE FROM mcp_permissions"))
        await conn.execute(text("DELETE FROM mcp_servers"))
        await conn.execute(text("DELETE FROM api_keys"))
        await conn.execute(text("DELETE FROM models"))
        await conn.execute(text("DELETE FROM providers"))
        await conn.execute(text("DELETE FROM groups"))
        await conn.execute(text("DELETE FROM agent_types"))
    await get_manager().refresh()
    yield
    await get_manager().refresh()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator:
    async with AsyncSessionLocal() as session:
        yield session
