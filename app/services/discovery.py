"""Auto-discovery of provider models + per-model workability test.

No hardcoded models: the provider's GET /models listing is parsed by
protocol (openai/anthropic: data[].id, gemini: models[].name). Each
discovered model gets a real minimal request to confirm it works.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal

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
        # retry on 429 (provider rate limiting) with backoff, max 3 retries
        attempts = 0
        while resp.status_code == 429 and attempts < 3:
            await resp.aclose()
            await asyncio.sleep(1.0 * (2**attempts))  # 1s, 2s, 4s
            resp = await pool.request(
                provider=provider,
                path=path,
                method="POST",
                json_body=body,
                request_id=request_id,
            )
            attempts += 1

        latency_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code < 400:
            await resp.aclose()
            return DiscoveredModelStatus(
                internal_model=internal_model, ok=True, category="ok", latency_ms=latency_ms
            )
        text = resp.text[:2000]
        await resp.aclose()
        if resp.status_code == 429:
            return DiscoveredModelStatus(
                internal_model=internal_model,
                ok=False,
                category="rate_limited",
                error="rate limited (429)",
            )
        error_msg = _extract_error(text, resp.status_code)
        category: Literal["premium", "error"] = "premium" if _is_premium(text) else "error"
        return DiscoveredModelStatus(
            internal_model=internal_model,
            ok=False,
            category=category,
            error=error_msg,
        )
    except Exception as exc:
        logger.warning("discovery.test_error", model=internal_model, error=type(exc).__name__)
        return DiscoveredModelStatus(
            internal_model=internal_model, ok=False, category="error", error=type(exc).__name__
        )


def _is_premium(body: str) -> bool:
    lowered = body.lower()
    hints = (
        "deposit",
        "premium",
        "access_denied",
        "restricted",
        "payment required",
        "insufficient balance",
        "credit",
        "billing",
        "balance=0",
        "insufficient_quota",
    )
    return any(h in lowered for h in hints)


def _extract_error(body: str, status_code: int) -> str:
    """Extract a human-readable error message from the provider's response body."""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            err = parsed.get("error") or {}
            if isinstance(err, dict):
                msg = err.get("message") or err.get("code") or ""
            elif isinstance(err, str):
                msg = err
            else:
                msg = ""
            if msg and isinstance(msg, str):
                return msg[:200]
    except (json.JSONDecodeError, TypeError):
        pass
    return f"HTTP {status_code}"


async def discover_and_test(
    provider: Provider, session: AsyncSession, request_id: str, test: bool = False
) -> ModelDiscoveryResult:
    discovered = await discover_provider_models(provider, request_id)
    imported = 0
    skipped = 0
    model_ids: dict[str, Model] = {}
    for mid in discovered:
        row = await session.execute(
            select(Model).where(
                Model.provider_id == provider.id,
                Model.user_model_id == mid,
            ).limit(1)
        )
        existing = row.scalar_one_or_none()
        if existing is None:
            m = Model(
                provider_id=provider.id,
                user_model_id=mid,
                internal_model=mid,
                is_active=1,
                meta="{}",
            )
            session.add(m)
            imported += 1
            model_ids[mid] = m
        else:
            skipped += 1
            model_ids[mid] = existing

    if not test:
        # light discover: list + import only, no real requests (avoids provider 429 sweeps)
        statuses = [
            DiscoveredModelStatus(internal_model=mid, ok=True, category="listed") for mid in discovered
        ]
        await session.commit()
        await get_manager().refresh()
        logger.info(
            "discovery.light_done",
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
            ok_count=len(discovered),
            models=statuses,
        )

    # full test: gentle pacing (providers 429 on bursts)
    sem = asyncio.Semaphore(2)

    async def _test(mid: str) -> DiscoveredModelStatus:
        async with sem:
            status = await test_provider_model(provider, mid, request_id)
            await asyncio.sleep(0.2)  # stagger
            return status

    statuses = list(await asyncio.gather(*[_test(mid) for mid in discovered]))

    # update premium flag in meta after tests
    for mid, status in zip(discovered, statuses, strict=False):
        if status.category == "premium":
            model_obj = model_ids.get(mid)
            if model_obj is not None:
                mmeta = json.loads(model_obj.meta or "{}")
                if not mmeta.get("premium"):
                    mmeta["premium"] = True
                    model_obj.meta = json.dumps(mmeta)

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
        models=list(statuses),
    )


__all__ = ["parse_model_list", "discover_provider_models", "test_provider_model", "discover_and_test"]
