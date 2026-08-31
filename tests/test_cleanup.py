"""Cleanup tests — soft deactivation, empty group delete, key deactivation, retention."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.models import AgentUsage, ApiKey, Group, Provider
from app.services.cleanup import run_cleanup


def _fake_resp(status_code: int = 200, json: dict | None = None, text: str = ""):
    async def _aclose() -> None:
        return None

    return SimpleNamespace(
        status_code=status_code,
        json=lambda: json or {},
        text=text,
        aclose=_aclose,
    )


async def _add_provider(name: str, protocol: str = "openai") -> str:
    async with AsyncSessionLocal() as session:
        p = Provider(name=name, base_url=f"https://{name}.test/v1", api_key="sk", protocol=protocol)
        session.add(p)
        await session.commit()
        return p.id


async def test_cleanup_deletes_empty_group() -> None:
    async with AsyncSessionLocal() as session:
        session.add(Group(name="orphan-group"))
        await session.commit()
    async with AsyncSessionLocal() as session:
        report = await run_cleanup(session)
    assert report.groups_deleted == 1


async def test_cleanup_keeps_group_with_key() -> None:
    async with AsyncSessionLocal() as session:
        g = Group(name="used-group")
        session.add(g)
        await session.commit()
        session.add(ApiKey(key_hash="h" * 64, group_id=g.id, monthly_budget=0))
        await session.commit()
    async with AsyncSessionLocal() as session:
        report = await run_cleanup(session)
    assert report.groups_deleted == 0


async def test_cleanup_deactivates_unreachable_provider(monkeypatch) -> None:
    import app.services.cleanup as cleanup

    async def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(cleanup, "discover_provider_models", _boom)
    pid = await _add_provider("dead-provider")
    async with AsyncSessionLocal() as session:
        report = await run_cleanup(session)
    async with AsyncSessionLocal() as session:
        p = (await session.execute(select(Provider).where(Provider.id == pid))).scalar_one()
    assert report.providers_deactivated == 1
    assert p.is_active == 0


async def test_cleanup_deactivates_inactive_key(monkeypatch) -> None:
    async with AsyncSessionLocal() as session:
        key = ApiKey(
            key_hash="a" * 64,
            monthly_budget=0,
            is_active=1,
            created_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=40),
        )
        session.add(key)
        await session.commit()
        key_id = key.id
    async with AsyncSessionLocal() as session:
        report = await run_cleanup(session)
    async with AsyncSessionLocal() as session:
        k = (await session.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one()
    assert report.keys_deactivated == 1
    assert k.is_active == 0


async def test_cleanup_retention_deletes_old_usage(monkeypatch) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            AgentUsage(
                agent_type="old-agent",
                tokens_in=10,
                tokens_out=5,
                cost_usd=0.0,
                created_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=100),
            )
        )
        await session.commit()
    async with AsyncSessionLocal() as session:
        report = await run_cleanup(session)
    assert report.usage_deleted == 1


async def test_cleanup_model_fail_count_and_deactivation(monkeypatch) -> None:
    import app.services.cleanup as cleanup
    from app.schemas import DiscoveredModelStatus

    async def _list_ok(*a, **k):
        return []

    async def _fail(*a, **k):
        return DiscoveredModelStatus(internal_model="x", ok=False, error="500 server_error")

    monkeypatch.setattr(cleanup, "discover_provider_models", _list_ok)
    monkeypatch.setattr(cleanup, "test_provider_model", _fail)

    pid = await _add_provider("fail-provider")
    async with AsyncSessionLocal() as session:
        from app.models import Model
        session.add(
            Model(
                provider_id=pid,
                user_model_id="flaky",
                internal_model="flaky",
                is_active=1,
                meta='{"test_fail_count":2,"missing_from_listing":true}',
            )
        )
        await session.commit()
    async with AsyncSessionLocal() as session:
        report = await run_cleanup(session)
    assert report.models_deactivated == 1


@pytest.mark.asyncio
async def test_cleanup_requires_panel_key(client) -> None:
    r = await client.post("/v1/admin/cleanup")
    assert r.status_code == 401
