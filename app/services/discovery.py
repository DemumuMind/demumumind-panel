"""Auto-discovery of provider models + per-model workability test.

No hardcoded models: the provider's GET /models listing is parsed by
protocol (openai/anthropic: data[].id, gemini: models[].name). Each
discovered model gets a real minimal request to confirm it works.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

import structlog
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UpstreamError
from app.models import Model, Provider, ProviderTestRun
from app.schemas import DiscoveredModelStatus, ModelDiscoveryResult
from app.services.failover import classify
from app.services.pool import get_pool
from app.services.provider_manager import get_manager
from app.services.translate import normalize_protocol

logger = structlog.get_logger(__name__)


def parse_model_list(provider: Provider, data: dict[str, Any]) -> list[str]:
    """Extract model ids from a provider's GET /models response by protocol."""
    return [mid for mid, _meta in parse_model_items(provider, data)]


def parse_model_items(provider: Provider, data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Extract (model_id, metadata) from a provider's GET /models response.

    metadata carries pricing/free/limits when the provider discloses them
    (OpenRouter: `pricing.{prompt,completion,request}`, `per_request_limits`).
    """
    proto = normalize_protocol(provider.protocol)
    raw: list[tuple[str, dict[str, Any]]] = []
    if proto == "gemini":
        for item in data.get("models") or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                raw.append((name.removeprefix("models/"), _model_meta_from_item(item)))
    else:
        for item in data.get("data") or []:
            if not isinstance(item, dict):
                continue
            mid = item.get("id")
            if isinstance(mid, str) and mid:
                raw.append((mid, _model_meta_from_item(item)))
    # dedupe, preserve order
    seen: set[str] = set()
    result: list[tuple[str, dict[str, Any]]] = []
    for mid, meta in raw:
        if mid not in seen:
            seen.add(mid)
            result.append((mid, meta))
    return result


def _model_meta_from_item(item: dict[str, Any]) -> dict[str, Any]:
    """Parse pricing/free/limits out of a /models item (OpenRouter-style)."""
    meta: dict[str, Any] = {}
    pricing_raw = item.get("pricing")
    if isinstance(pricing_raw, dict):
        pricing: dict[str, float] = {}
        for key in ("prompt", "completion", "request"):
            val = pricing_raw.get(key)
            if isinstance(val, (int | float)) and not isinstance(val, bool):
                pricing[key] = float(val)
            elif isinstance(val, str):
                with contextlib.suppress(ValueError):
                    pricing[key] = float(val)
        if pricing:
            meta["pricing"] = pricing
    mid = str(item.get("id") or "")
    pricing = meta.get("pricing") or {}
    free = mid.endswith(":free") or mid.endswith("-free") or (
        pricing and all(pricing.get(k, 0.0) == 0.0 for k in ("prompt", "completion", "request"))
    )
    if free:
        meta["free"] = True
    limits_raw = item.get("per_request_limits")
    if isinstance(limits_raw, dict):
        limits: dict[str, Any] = {}
        for key in ("prompt_tokens", "completion_tokens"):
            if limits_raw.get(key) is not None:
                limits[key] = limits_raw[key]
        if limits:
            meta["limits"] = limits
    return meta


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


async def discover_provider_models_with_meta(provider: Provider, request_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Like discover_provider_models but returns (id, metadata) pairs.

    metadata carries pricing/free/limits from the provider's /models listing
    (OpenRouter: `pricing`, `per_request_limits`, `:free` suffix).
    """
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
    return parse_model_items(provider, data)


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


def _merge_provider_meta(existing_meta: dict[str, Any], discovered_meta: dict[str, Any]) -> bool:
    """Merge provider-discovered pricing/free/limits into model meta.

    Manual override (price_source == 'manual') is never overwritten.
    Returns True if meta changed.
    """
    if not discovered_meta:
        return False
    if existing_meta.get("price_source") == "manual":
        return False
    changed = False
    pricing = discovered_meta.get("pricing")
    if isinstance(pricing, dict):
        merged = dict(existing_meta.get("pricing") or {})
        for key, val in pricing.items():
            if merged.get(key) != val:
                merged[key] = val
                changed = True
        existing_meta["pricing"] = merged
    if "free" in discovered_meta and existing_meta.get("free") != discovered_meta["free"]:
        existing_meta["free"] = discovered_meta["free"]
        changed = True
    limits = discovered_meta.get("limits")
    if isinstance(limits, dict):
        merged_limits = dict(existing_meta.get("limits") or {})
        for key, val in limits.items():
            if merged_limits.get(key) != val:
                merged_limits[key] = val
                changed = True
        existing_meta["limits"] = merged_limits
    return changed


async def discover_and_test(
    provider: Provider, session: AsyncSession, request_id: str, test: bool = False
) -> ModelDiscoveryResult:
    discovered = await discover_provider_models_with_meta(provider, request_id)
    imported = 0
    skipped = 0
    model_ids: dict[str, Model] = {}
    for mid, dmeta in discovered:
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
                meta=json.dumps(dmeta) if dmeta else "{}",
            )
            session.add(m)
            imported += 1
            model_ids[mid] = m
        else:
            skipped += 1
            if dmeta:
                mmeta = json.loads(existing.meta or "{}")
                if _merge_provider_meta(mmeta, dmeta):
                    existing.meta = json.dumps(mmeta)
            model_ids[mid] = existing

    if not test:
        # light discover: list + import only, no real requests (avoids provider 429 sweeps)
        statuses = [
            DiscoveredModelStatus(internal_model=mid, ok=True, category="listed") for mid, _meta in discovered
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

    statuses = list(await asyncio.gather(*[_test(mid) for mid, _ in discovered]))

    # update premium flag in meta after tests
    for (mid, _), status in zip(discovered, statuses, strict=False):
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


async def _save_test_run(
    session: AsyncSession, provider: Provider, kind: str, result: ModelDiscoveryResult
) -> None:
    """Persist a test/discover run to history, capped at 100 runs per provider."""
    session.add(
        ProviderTestRun(
            provider_id=provider.id,
            provider_name=provider.name,
            kind=kind,
            result=json.dumps(result.model_dump(), ensure_ascii=False),
            ok_count=result.ok_count,
            total=result.total,
        )
    )
    # cap: delete oldest beyond the newest 100 for this provider
    total = await session.execute(
        select(func.count()).select_from(ProviderTestRun).where(ProviderTestRun.provider_id == provider.id)
    )
    count = int(total.scalar_one() or 0)
    if count > 100:
        excess = await session.execute(
            select(ProviderTestRun.id)
            .where(ProviderTestRun.provider_id == provider.id)
            .order_by(ProviderTestRun.created_at.desc())
            .offset(100)
        )
        ids = [row[0] for row in excess.all()]
        if ids:
            await session.execute(sa_delete(ProviderTestRun).where(ProviderTestRun.id.in_(ids)))
            logger.info("discovery.test_run_capped", provider=provider.name, removed=len(ids))


async def discover_and_test_stream(
    provider: Provider, session: AsyncSession, request_id: str, test: bool = False
) -> AsyncIterator[dict[str, Any]]:
    """Discover + optional full test, yielding live SSE progress events.

    Events:
      {"event":"stage","stage":"listing"}
      {"event":"stage","stage":"import","total":N}
      {"event":"import","current":i,"total":N,"model":m,"status":"imported|skipped"}
      {"event":"stage","stage":"test","total":N}            (only when test=True)
      {"event":"test","current":i,"total":N,"model":m,"ok":b,"category":c,"error":e,"latency_ms":ms}
      {"event":"done","result":{...ModelDiscoveryResult...}}
    """
    yield {"event": "stage", "stage": "listing", "message": "Fetching models…"}
    discovered = await discover_provider_models_with_meta(provider, request_id)
    imported = 0
    skipped = 0
    model_ids: dict[str, Model] = {}
    total = len(discovered)
    yield {"event": "stage", "stage": "import", "total": total}
    for mid, dmeta in discovered:
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
                meta=json.dumps(dmeta) if dmeta else "{}",
            )
            session.add(m)
            imported += 1
            model_ids[mid] = m
            yield {"event": "import", "current": imported + skipped, "total": total, "model": mid, "status": "imported"}
        else:
            skipped += 1
            if dmeta:
                mmeta = json.loads(existing.meta or "{}")
                if _merge_provider_meta(mmeta, dmeta):
                    existing.meta = json.dumps(mmeta)
            model_ids[mid] = existing
            yield {"event": "import", "current": imported + skipped, "total": total, "model": mid, "status": "skipped"}

    if not test:
        statuses = [
            DiscoveredModelStatus(internal_model=mid, ok=True, category="listed") for mid, _ in discovered
        ]
        result = ModelDiscoveryResult(
            provider_id=provider.id,
            provider_name=provider.name,
            total=len(discovered),
            imported=imported,
            skipped=skipped,
            ok_count=len(discovered),
            models=statuses,
        )
        await _save_test_run(session, provider, kind="discover", result=result)
        await session.commit()
        await get_manager().refresh()
        yield {"event": "done", "result": result.model_dump()}
        return

    # full test: bounded concurrency + live events as each completes
    yield {"event": "stage", "stage": "test", "total": total}
    sem = asyncio.Semaphore(2)

    async def _test(mid: str) -> tuple[str, DiscoveredModelStatus]:
        async with sem:
            status = await test_provider_model(provider, mid, request_id)
            await asyncio.sleep(0.2)  # stagger
            return mid, status

    tasks = [asyncio.create_task(_test(mid)) for mid, _ in discovered]
    status_map: dict[str, DiscoveredModelStatus] = {}
    for done_count, coro in enumerate(asyncio.as_completed(tasks), 1):
        mid, status = await coro
        status_map[mid] = status
        yield {
            "event": "test",
            "current": done_count,
            "total": total,
            "model": mid,
            "ok": status.ok,
            "category": status.category,
            "error": status.error,
            "latency_ms": status.latency_ms,
        }
        if status.category == "premium":
            model_obj = model_ids.get(mid)
            if model_obj is not None:
                mmeta = json.loads(model_obj.meta or "{}")
                if not mmeta.get("premium"):
                    mmeta["premium"] = True
                    model_obj.meta = json.dumps(mmeta)

    ordered = [status_map[mid] for mid, _ in discovered]
    result = ModelDiscoveryResult(
        provider_id=provider.id,
        provider_name=provider.name,
        total=len(discovered),
        imported=imported,
        skipped=skipped,
        ok_count=sum(1 for s in ordered if s.ok),
        models=ordered,
    )
    await _save_test_run(session, provider, kind="test", result=result)
    await session.commit()
    await get_manager().refresh()
    yield {"event": "done", "result": result.model_dump()}


__all__ = [
    "parse_model_list",
    "parse_model_items",
    "discover_provider_models",
    "discover_provider_models_with_meta",
    "test_provider_model",
    "discover_and_test",
    "discover_and_test_stream",
]
