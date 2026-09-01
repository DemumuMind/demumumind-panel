"""ProviderManager tests — insert, resolve, per-key mapping, pagination."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas import CreateApiKeyRequest
from app.services.provider_manager import get_manager
from tests.conftest import ADMIN_HEADERS


async def _add_provider_and_model(client: AsyncClient) -> tuple[str, str]:
    rp = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={
            "name": "ProvA",
            "base_url": "https://a.test/v1",
            "api_key": "sk-a",
            "protocol": "openai",
            "is_default": True,
        },
    )
    assert rp.status_code == 201, rp.text
    provider_id = rp.json()["id"]
    rm = await client.post(
        "/v1/admin/models",
        headers=ADMIN_HEADERS,
        json={"provider_id": provider_id, "user_model_id": "my-sonnet", "internal_model": "sonnet-x"},
    )
    assert rm.status_code == 201, rm.text
    return provider_id, "my-sonnet"


async def test_insert_and_resolve(client: AsyncClient) -> None:
    await _add_provider_and_model(client)
    resolved = get_manager().resolve("my-sonnet")
    assert resolved is not None
    assert resolved.internal_model == "sonnet-x"
    assert resolved.provider_name == "ProvA"
    assert resolved.protocol == "openai"


async def test_resolve_unknown_model(client: AsyncClient) -> None:
    await _add_provider_and_model(client)
    assert get_manager().resolve("nope") is None


async def test_per_key_model_mapping(client: AsyncClient) -> None:
    await _add_provider_and_model(client)
    rk = await client.post("/v1/admin/keys", headers=ADMIN_HEADERS, json={"model_mapping": {}})
    assert rk.status_code == 201
    raw_key = rk.json()["api_key"]
    # key maps "alias" -> "my-sonnet"
    rk2 = await client.post(
        "/v1/admin/keys",
        headers=ADMIN_HEADERS,
        json={"model_mapping": {"alias": "my-sonnet"}},
    )
    assert rk2.status_code == 201
    raw_key2 = rk2.json()["api_key"]

    from app.api.v1.middleware import hash_key

    key_hash1 = hash_key(raw_key)
    key_hash2 = hash_key(raw_key2)
    assert get_manager().resolve("alias", key_hash1) is None
    resolved = get_manager().resolve("alias", key_hash2)
    assert resolved is not None
    assert resolved.user_model_id == "my-sonnet"


async def test_list_models_pagination(client: AsyncClient) -> None:
    await _add_provider_and_model(client)
    page = await get_manager().list_available_models_detailed(limit=10, offset=0)
    assert page.total == 1
    assert page.items[0]["user_model_id"] == "my-sonnet"


async def test_duplicate_user_model_409(client: AsyncClient) -> None:
    provider_id, _ = await _add_provider_and_model(client)
    resp = await client.post(
        "/v1/admin/models",
        headers=ADMIN_HEADERS,
        json={"provider_id": provider_id, "user_model_id": "my-sonnet", "internal_model": "other"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "duplicate"


async def test_same_alias_two_providers_allowed(client: AsyncClient) -> None:
    """Composite unique (provider_id, user_model_id) allows same alias across providers."""
    rp1 = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "P1", "base_url": "https://p1.test/v1", "api_key": "k", "protocol": "openai"},
    )
    rp2 = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "P2", "base_url": "https://p2.test/v1", "api_key": "k", "protocol": "openai"},
    )
    pid1, pid2 = rp1.json()["id"], rp2.json()["id"]
    m1 = await client.post(
        "/v1/admin/models",
        headers=ADMIN_HEADERS,
        json={"provider_id": pid1, "user_model_id": "shared-alias", "internal_model": "internal-1"},
    )
    assert m1.status_code == 201
    m2 = await client.post(
        "/v1/admin/models",
        headers=ADMIN_HEADERS,
        json={"provider_id": pid2, "user_model_id": "shared-alias", "internal_model": "internal-2"},
    )
    assert m2.status_code == 201, m2.text
    # global alias resolves to the first/default match
    resolved = get_manager().resolve("shared-alias")
    assert resolved is not None
    # explicit provider/alias routing works
    resolved2 = get_manager().resolve("P2/shared-alias")
    assert resolved2 is not None
    assert resolved2.internal_model == "internal-2"
    assert resolved2.provider_name == "P2"


async def test_api_key_created_once_and_hashed(client: AsyncClient) -> None:
    resp = await client.post("/v1/admin/keys", headers=ADMIN_HEADERS, json={"monthly_budget": 50})
    assert resp.status_code == 201
    data = resp.json()
    assert data["api_key"].startswith("dm-")

    assert get_manager()._key_mappings  # noqa: SLF001  (loaded after refresh)


@pytest.mark.asyncio
async def test_budget_defaults(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/admin/keys", headers=ADMIN_HEADERS, json=CreateApiKeyRequest().model_dump()
    )
    assert resp.status_code == 201
