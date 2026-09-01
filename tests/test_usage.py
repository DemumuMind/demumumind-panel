"""Usage pricing tests — cost extraction, free detection, aggregation, PATCH pricing."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.services.discovery import parse_model_items
from app.services.dispatch import _compute_cost_from_pricing, _cost_from_usage, _resolve_cost
from app.services.finops import get_finops
from app.services.provider_manager import ResolvedModel
from tests.conftest import ADMIN_HEADERS


def _resolved(**kw) -> ResolvedModel:
    base = dict(
        user_model_id="m",
        internal_model="m",
        provider_id="p",
        provider_name="Prov",
        base_url="https://x",
        protocol="openai",
        api_key="k",
    )
    base.update(kw)
    return ResolvedModel(**base)


# --- cost extraction ---


async def test_cost_from_usage_openrouter() -> None:
    assert _cost_from_usage({"cost": 0.00014}) == 0.00014
    assert _cost_from_usage({"cost": "0.00014"}) is None  # strings not trusted
    assert _cost_from_usage({"cost": 0}) == 0.0


async def test_cost_from_usage_details() -> None:
    usage = {"cost_details": {"upstream_inference_prompt_cost": 0.0001, "upstream_inference_completions_cost": 0.0002}}
    assert _cost_from_usage(usage) == pytest.approx(0.0003)


async def test_cost_from_usage_none() -> None:
    assert _cost_from_usage(None) is None
    assert _cost_from_usage({}) is None


async def test_compute_cost_from_pricing() -> None:
    r = _resolved(pricing={"prompt": 0.000001, "completion": 0.000002, "request": 0.0005})
    cost = _compute_cost_from_pricing(r, tokens_in=1000, tokens_out=500)
    assert cost == pytest.approx(0.001 + 0.001 + 0.0005)


async def test_compute_cost_no_pricing_none() -> None:
    assert _compute_cost_from_pricing(_resolved(), 1000, 500) is None


async def test_resolve_cost_priority_provider_wins() -> None:
    r = _resolved(pricing={"prompt": 1e-6, "completion": 2e-6})
    data = {"usage": {"cost": 0.00014}}
    cost, known = _resolve_cost(r, data, 1000, 500)
    assert cost == 0.00014
    assert known is True


async def test_resolve_cost_fallback_pricing() -> None:
    r = _resolved(pricing={"prompt": 1e-6, "completion": 2e-6})
    data = {"usage": {"prompt_tokens": 1000, "completion_tokens": 500}}
    cost, known = _resolve_cost(r, data, tokens_in=1000, tokens_out=500)
    assert known is True
    assert cost == pytest.approx(0.001 + 0.001)


async def test_resolve_cost_unknown() -> None:
    r = _resolved()
    data = {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    cost, known = _resolve_cost(r, data)
    assert known is False
    assert cost == 0.0


# --- /models parsing ---


async def test_parse_model_items_pricing_free() -> None:
    from app.models import Provider

    p = Provider(protocol="openai")
    items = parse_model_items(
        p,
        {
            "data": [
                {"id": "openai/gpt-4o", "pricing": {"prompt": "0.0000025", "completion": "0.00001", "request": "0"}},
                {"id": "z-ai/glm-4.5:free", "pricing": {"prompt": "0", "completion": "0", "request": "0"}},
                {"id": "plain-model"},
            ]
        },
    )
    by_id = {mid: meta for mid, meta in items}
    assert by_id["openai/gpt-4o"]["pricing"] == pytest.approx({"prompt": 2.5e-6, "completion": 1e-5, "request": 0.0})
    assert "free" not in by_id["openai/gpt-4o"]
    assert by_id["z-ai/glm-4.5:free"]["free"] is True
    assert "free" not in by_id["plain-model"]


async def test_parse_model_items_limits() -> None:
    from app.models import Provider

    p = Provider(protocol="openai")
    payload = {"data": [{"id": "m", "per_request_limits": {"prompt_tokens": 1000, "completion_tokens": 500}}]}
    items = parse_model_items(p, payload)
    assert items[0][1]["limits"] == {"prompt_tokens": 1000, "completion_tokens": 500}


# --- aggregation with new columns ---


async def test_usage_aggregation_columns(client: AsyncClient, db_session) -> None:
    finops = get_finops()
    await finops.record_usage(
        db_session,
        agent_type="key_abcd",
        provider_id=None,
        model_id=None,
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.0,
        is_free=True,
        price_known=True,
        cache_hit=False,
    )
    await finops.record_usage(
        db_session,
        agent_type="key_abcd",
        provider_id=None,
        model_id=None,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        is_free=False,
        price_known=False,
        cache_hit=True,
    )
    r = await client.get("/v1/usage?limit=10&offset=0", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    row = data["items"][0]
    assert row["requests"] == 2
    assert row["free_requests"] == 1
    assert row["unknown_requests"] == 1
    assert row["cached_requests"] == 1


# --- PATCH pricing endpoint ---


async def test_update_model_pricing_manual(client: AsyncClient) -> None:
    rp = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "PriceProv", "base_url": "https://p.test/v1", "api_key": "sk", "protocol": "openai"},
    )
    provider_id = rp.json()["id"]
    rm = await client.post(
        "/v1/admin/models",
        headers=ADMIN_HEADERS,
        json={"provider_id": provider_id, "user_model_id": "m1", "internal_model": "m1"},
    )
    model_id = rm.json()["id"]

    resp = await client.patch(
        f"/v1/admin/models/{model_id}/pricing",
        headers=ADMIN_HEADERS,
        json={
            "price_prompt_per_token": 1e-6,
            "price_completion_per_token": 2e-6,
            "free": True,
            "limit_requests_per_day": 200,
        },
    )
    assert resp.status_code == 200, resp.text
    meta = resp.json()["metadata"]
    assert meta["free"] is True
    assert meta["price_source"] == "manual"
    assert meta["pricing"]["prompt"] == 1e-6
    assert meta["limits"]["requests_per_day"] == 200


async def test_update_model_pricing_preserves_manual(client: AsyncClient, monkeypatch) -> None:
    """Discovery must not overwrite a manual pricing override."""
    import app.services.discovery as discovery

    async def _req(**kw):
        class R:
            status_code = 200

            def json(self):
                return {"data": [{"id": "m1", "pricing": {"prompt": "0", "completion": "0", "request": "0"}}]}

            async def aclose(self):
                return None

        return R()

    monkeypatch.setattr(discovery.get_pool(), "request", _req)

    rp = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "ManualProv", "base_url": "https://mp.test/v1", "api_key": "sk", "protocol": "openai"},
    )
    provider_id = rp.json()["id"]
    rm = await client.post(
        "/v1/admin/models",
        headers=ADMIN_HEADERS,
        json={"provider_id": provider_id, "user_model_id": "m1", "internal_model": "m1"},
    )
    model_id = rm.json()["id"]
    await client.patch(
        f"/v1/admin/models/{model_id}/pricing",
        headers=ADMIN_HEADERS,
        json={"price_prompt_per_token": 5e-6, "free": False},
    )
    r = await client.post(f"/v1/admin/providers/{provider_id}/discover", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    mr = await client.get(f"/v1/admin/models?provider_id={provider_id}&limit=10&offset=0", headers=ADMIN_HEADERS)
    meta = mr.json()["items"][0]["metadata"]
    assert meta["price_source"] == "manual"
    assert meta["pricing"]["prompt"] == 5e-6  # unchanged despite provider saying 0


async def test_manual_pricing_reconciles_existing_rows(client: AsyncClient, db_session) -> None:
    """Setting manual pricing on a model recomputes its existing usage rows."""
    from app.models import AgentUsage
    from app.services.finops import get_finops

    rp = await client.post(
        "/v1/admin/providers",
        headers=ADMIN_HEADERS,
        json={"name": "ReconcileProv", "base_url": "https://r.test/v1", "api_key": "sk", "protocol": "openai"},
    )
    provider_id = rp.json()["id"]
    rm = await client.post(
        "/v1/admin/models",
        headers=ADMIN_HEADERS,
        json={"provider_id": provider_id, "user_model_id": "m-recon", "internal_model": "m-recon"},
    )
    model_id = rm.json()["id"]

    finops = get_finops()
    await finops.record_usage(
        db_session,
        agent_type="key_x",
        provider_id=provider_id,
        model_id=model_id,
        tokens_in=1000,
        tokens_out=500,
        cost_usd=0.0,
        is_free=False,
        price_known=False,
    )

    resp = await client.patch(
        f"/v1/admin/models/{model_id}/pricing",
        headers=ADMIN_HEADERS,
        json={"price_prompt_per_token": 1e-6, "price_completion_per_token": 2e-6, "free": True},
    )
    assert resp.status_code == 200

    rows = (await db_session.execute(select(AgentUsage).where(AgentUsage.model_id == model_id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].price_known == 1
    assert rows[0].is_free == 1
    assert rows[0].cost_usd == pytest.approx(0.001 + 0.001)


__all__: list[str] = []