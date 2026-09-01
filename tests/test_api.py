"""API integration tests — health, auth, pagination, CRUD."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import ADMIN_HEADERS


async def test_health_ok(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.2.0"
    assert data["checks"]["db"] == "ok"


async def test_health_has_request_id(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert "x-request-id" in r.headers


async def test_health_no_auth_required(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200


async def test_v1_models_no_key_401(client: AsyncClient) -> None:
    r = await client.get("/v1/models")
    assert r.status_code == 401
    assert "unauthorized" in r.json()["error"]


async def test_admin_no_key_401(client: AsyncClient) -> None:
    r = await client.get("/v1/admin/providers")
    assert r.status_code == 401


async def test_admin_bad_key_401(client: AsyncClient) -> None:
    r = await client.get("/v1/admin/providers", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


async def test_seed_idempotent(client: AsyncClient) -> None:
    r1 = await client.post("/v1/admin/seed", headers=ADMIN_HEADERS)
    assert r1.status_code == 200
    r2 = await client.post("/v1/admin/seed", headers=ADMIN_HEADERS)
    assert r2.status_code == 200
    # groups=0 on second call (already exist)
    assert r2.json()["groups"] == 0


async def test_create_provider_201(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "NewProv", "base_url": "https://api.new.com/v1", "protocol": "openai", "is_default": True},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "NewProv"
    assert data["is_default"] is True
    assert data["metadata"] == {}


async def test_create_provider_duplicate_409(client: AsyncClient) -> None:
    await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "DupProv", "base_url": "https://a.com/v1", "protocol": "openai"},
    )
    r2 = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "DupProv", "base_url": "https://b.com/v1", "protocol": "openai"},
    )
    assert r2.status_code == 409
    assert r2.json()["error"] == "duplicate"


async def test_list_providers_pagination(client: AsyncClient) -> None:
    for i in range(3):
        await client.post(
            "/v1/admin/providers",
            headers=ADMIN_HEADERS,
            json={"name": f"P{i}", "base_url": f"https://p{i}.com/v1", "protocol": "openai"},
        )
    r = await client.get("/v1/admin/providers?limit=2&offset=0", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["offset"] == 0
    assert data["limit"] == 2


async def test_create_key_returns_raw_once(client: AsyncClient) -> None:
    r = await client.post("/v1/admin/keys", headers=ADMIN_HEADERS, json={"monthly_budget": 100})
    assert r.status_code == 201
    data = r.json()
    assert "api_key" in data
    assert data["api_key"].startswith("dm-")
    # second call gives different key — raw key not stored
    r2 = await client.post("/v1/admin/keys", headers=ADMIN_HEADERS, json={})
    assert r2.status_code == 201
    assert r2.json()["api_key"] != data["api_key"]


async def test_delete_key(client: AsyncClient) -> None:
    r = await client.post("/v1/admin/keys", headers=ADMIN_HEADERS, json={})
    key_id = r.json()["id"]
    rd = await client.delete(f"/v1/admin/keys/{key_id}", headers=ADMIN_HEADERS)
    assert rd.status_code == 200
    assert rd.json()["ok"] is True


async def test_delete_key_not_found(client: AsyncClient) -> None:
    r = await client.delete("/v1/admin/keys/nope", headers=ADMIN_HEADERS)
    assert r.status_code == 404