"""Auto-discovery of provider models + per-model workability test.

No hardcoded models: the provider's GET /models listing is parsed by
protocol (openai/anthropic: data[].id, gemini: models[].name). Each
discovered model gets a real minimal request to confirm it works.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UpstreamError
from app.models import Model, Provider
from app.schemas import DiscoveredModelStatus, ModelDiscoveryResult
from app.services.failover import classify
from app.services.pool import get_pool
from app.services.provider_manager import get_manager
from app.services.translate import normalize_protocol

logger = structlog.get_logger(__name__)


def parse_model_list(provider: Provider, data: dict[str, Any]) -> list[str]:
    """Extract model ids from a provider's GET /models response by protocol."""
    proto = normalize_protocol(provider.protocol)
    out: list[str] = []
    if proto == "gemini":
        for item in data.get("models") or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                out.append(name.removeprefix("models/"))
    else:
        for item in data.get("data") or []:
            if not isinstance(item, dict):
                continue
            mid = item.get("id")
            if isinstance(mid, str) and mid:
                out.append(mid)
    # dedupe, preserve order
    seen: set[str] = set()
    result: list[str] = []
    for m in out:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


async def discover_provider_models(provider: Provider, request_id: str) -> list[str]:
    pool = get_pool()
    try:
        resp = await pool.request(
            provider=provider,
            path="models",
            method="GET",
            json_body=None,
            request_id=request_id,
        )
    except Exception as exc:
        raise UpstreamError(
            status_code=502,
            message="Provider /models unreachable",
            detail=type(exc).__name__,
            request_id=request_id,
        ) from exc
    if resp.status_code >= 400:
        body = resp.text[:2000]
        decision = classify(resp.status_code, body)
        await resp.aclose()
        raise UpstreamError(
            status_code=resp.status_code,
            message=f"Provider /models failed ({decision.category})",
            detail=body[:300],
            request_id=request_id,
        )
    data = resp.json()
    await resp.aclose()
    return parse_model_list(provider, data)


def _test_body(protocol: str, internal_model: str) -> tuple[str, dict[str, Any]]:
    proto = normalize_protocol(protocol)
    if proto == "anthropic":
        return "v1/messages", {
            "model": internal_model,
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "ping"}],
        }
    if proto == "gemini":
        return f"v1beta/models/{internal_model}:generateContent", {
            "contents": [{"parts": [{"text": "ping"}]}]
        }
    return "chat/completions", {
        "model": internal_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }


async def test_provider_model(
    provider: Provider, internal_model: str, request_id: str
) -> DiscoveredModelStatus:
    path, body = _test_body(provider.protocol, internal_model)
    pool = get_pool()
    start = time.monotonic()
    try:
        resp = await pool.request(
            provider=provider,
            path=path,
            method="POST",
            json_body=body,
            request_id=request_id,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code < 400:
            await resp.aclose()
            return DiscoveredModelStatus(internal_model=internal_model, ok=True, latency_ms=latency_ms)
        text = resp.text[:1000]
        await resp.aclose()
        decision = classify(resp.status_code, text)
        return DiscoveredModelStatus(
            internal_model=internal_model,
            ok=False,
            error=f"{resp.status_code} {decision.category}",
        )
    except Exception as exc:
        logger.warning("discovery.test_error", model=internal_model, error=type(exc).__name__)
        return DiscoveredModelStatus(internal_model=internal_model, ok=False, error=type(exc).__name__)


async def discover_and_test(
    provider: Provider, session: AsyncSession, request_id: str
) -> ModelDiscoveryResult:
    discovered = await discover_provider_models(provider, request_id)
    imported = 0
    skipped = 0
    statuses: list[DiscoveredModelStatus] = []
    for mid in discovered:
        existing = await session.execute(
            select(Model).where(
                Model.provider_id == provider.id,
                Model.user_model_id == mid,
            ).limit(1)
        )
        if existing.scalar_one_or_none() is None:
            session.add(
                Model(
                    provider_id=provider.id,
                    user_model_id=mid,
                    internal_model=mid,
                    is_active=1,
                    meta="{}",
                )
            )
            imported += 1
        else:
            skipped += 1
        statuses.append(await test_provider_model(provider, mid, request_id))
    await session.commit()
    await get_manager().refresh()
    logger.info(
        "discovery.done",
        provider=provider.name,
        total=len(discovered),
        imported=imported,
        skipped=skipped,
    )
    return ModelDiscoveryResult(
        provider_id=provider.id,
        provider_name=provider.name,
        total=len(discovered),
        imported=imported,
        skipped=skipped,
        ok_count=sum(1 for s in statuses if s.ok),
        models=statuses,
    )


__all__ = ["parse_model_list", "discover_provider_models", "test_provider_model", "discover_and_test"]
