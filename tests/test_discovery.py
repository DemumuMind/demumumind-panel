"""Discovery tests — protocol parsing, auto-import, workability test."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.models import Provider
from app.services.discovery import parse_model_list
from app.services.discovery import test_provider_model as service_test_model
from tests.conftest import ADMIN_HEADERS


def _fake_resp(status_code: int = 200, json: dict | None = None, text: str = ""):
    async def _aclose() -> None:
        return None

    return SimpleNamespace(
        status_code=status_code,
        json=lambda: json or {},
        text=text,
        aclose=_aclose,
    )


async def test_parse_openai() -> None:
    provider = Provider(protocol="openai")
    ids = parse_model_list(provider, {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}, {}]})
    assert ids == ["gpt-4o", "gpt-4o-mini"]


async def test_parse_anthropic() -> None:
    provider = Provider(protocol="anthropic")
    ids = parse_model_list(provider, {"data": [{"id": "claude-sonnet-4-5"}]})
    assert ids == ["claude-sonnet-4-5"]


async def test_parse_gemini() -> None:
    provider = Provider(protocol="gemini")
    ids = parse_model_list(provider, {"models": [{"name": "models/gemini-2.0-flash"}, {"name": "gemini-1.5-pro"}]})
    assert ids == ["gemini-2.0-flash", "gemini-1.5-pro"]


async def test_parse_bad_shape_no_raise() -> None:
    provider = Provider(protocol="openai")
    assert parse_model_list(provider, {}) == []
    assert parse_model_list(provider, {"data": "nope"}) == []


async def test_test_provider_model_ok(monkeypatch) -> None:
    import app.services.discovery as discovery

    async def _req(**kw):
        return _fake_resp(200, {"choices": [{"message": {"content": "pong"}}]})

    monkeypatch.setattr(discovery.get_pool(), "request", _req)
    provider = Provider(protocol="openai", base_url="https://x/v1", api_key="k")
    status = await service_test_model(provider, "gpt-4o", "req-1")
    assert status.ok is True
    assert status.latency_ms is not None


async def test_test_provider_model_error(monkeypatch) -> None:
    import app.services.discovery as discovery

    async def _req(**kw):
        return _fake_resp(401, text='{"error": "unauthorized"}')

    monkeypatch.setattr(discovery.get_pool(), "request", _req)
    provider = Provider(protocol="openai", base_url="https://x/v1", api_key="k")
    status = await service_test_model(provider, "gpt-4o", "req-1")
    assert status.ok is False
    assert status.error


async def test_discover_auto_imports_all(client: AsyncClient, monkeypatch) -> None:
    import app.services.discovery as discovery

    async def _req(**kw):
        if kw["path"] == "models":
            return _fake_resp(200, {"data": [{"id": "m1"}, {"id": "m2"}]})
        return _fake_resp(200, {"choices": [{"message": {"content": "pong"}}]})

    monkeypatch.setattr(discovery.get_pool(), "request", _req)
    rp = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "Disc", "base_url": "https://d.test/v1", "api_key": "sk", "protocol": "openai"},
    )
    assert rp.status_code == 201
    pid = rp.json()["id"]

    r = await client.post(f"/v1/admin/providers/{pid}/discover", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert data["imported"] == 2
    assert data["skipped"] == 0
    assert data["ok_count"] == 2
    assert {m["internal_model"] for m in data["models"]} == {"m1", "m2"}

    # models now visible in listing
    models = await client.get("/v1/admin/models", headers=ADMIN_HEADERS)
    assert models.status_code == 200
    user_ids = {m["user_model_id"] for m in models.json()["items"]}
    assert {"m1", "m2"} <= user_ids


async def test_discover_skips_existing(client: AsyncClient, monkeypatch) -> None:
    import app.services.discovery as discovery

    async def _req(**kw):
        return _fake_resp(200, {"data": [{"id": "m1"}]})

    monkeypatch.setattr(discovery.get_pool(), "request", _req)
    rp = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "Disc2", "base_url": "https://d2.test/v1", "api_key": "sk", "protocol": "openai"},
    )
    pid = rp.json()["id"]

    await client.post(f"/v1/admin/providers/{pid}/discover", headers=ADMIN_HEADERS)
    r2 = await client.post(f"/v1/admin/providers/{pid}/discover", headers=ADMIN_HEADERS)
    data = r2.json()
    assert data["total"] == 1
    assert data["imported"] == 0
    assert data["skipped"] == 1


@pytest.mark.asyncio
async def test_discover_requires_panel_key(client: AsyncClient) -> None:
    rp = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "Disc3", "base_url": "https://d3.test/v1", "api_key": "sk", "protocol": "openai"},
    )
    pid = rp.json()["id"]
    r = await client.post(f"/v1/admin/providers/{pid}/discover")
    assert r.status_code == 401
