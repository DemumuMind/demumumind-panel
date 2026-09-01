"""Dispatch — orchestrates a single LLM call end-to-end.

Flow: resolve -> guardrails.validate_input -> cache.get -> translate_request
-> pool.request (with failover classify) -> translate_response ->
guardrails.validate_output -> cache.set -> telemetry. Every path carries
X-Request-ID; errors are AppError/UpstreamError values, never panics.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

import structlog

from app.core.db import AsyncSessionLocal
from app.core.errors import NotFoundError, UpstreamError
from app.models import Provider
from app.services.cache import get_cache
from app.services.failover import classify
from app.services.finops import get_finops
from app.services.guardrails import get_guardrail
from app.services.pool import get_pool
from app.services.provider_manager import ResolvedModel, get_manager
from app.services.telemetry import record_latency, record_usage
from app.services.translate import normalize_protocol, translate_request, translate_response

logger = structlog.get_logger(__name__)


@dataclass
class CacheMarker:
    hit: bool = False


def _provider_path(protocol: str, model: str) -> str:
    proto = normalize_protocol(protocol)
    if proto == "anthropic":
        return "v1/messages"
    if proto == "gemini":
        return f"v1beta/models/{model}:generateContent"
    if proto == "cohere":
        return "v2/chat"
    if proto == "ollama":
        return "api/chat"
    return "chat/completions"


def _extract_prompt(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    parts.append(str(block["text"]))
    return "\n".join(parts)[:8000]


def _tokens_from(data: dict[str, Any], protocol: str) -> tuple[int, int]:
    usage = data.get("usage") or {}
    proto = normalize_protocol(protocol)
    if proto == "anthropic":
        return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    if proto == "gemini":
        um = data.get("usageMetadata") or {}
        return int(um.get("promptTokenCount", 0)), int(um.get("candidatesTokenCount", 0))
    return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


def _cost_from_usage(usage: dict[str, Any] | None) -> float | None:
    """Real USD cost reported by the provider (OpenRouter `usage.cost`)."""
    if not isinstance(usage, dict):
        return None
    cost = usage.get("cost")
    if isinstance(cost, (int | float)) and not isinstance(cost, bool):
        return float(cost)
    details = usage.get("cost_details")
    if isinstance(details, dict):
        p = details.get("upstream_inference_prompt_cost")
        c = details.get("upstream_inference_completions_cost")
        if isinstance(p, (int | float)) and isinstance(c, (int | float)):
            return float(p) + float(c)
    return None


def _compute_cost_from_pricing(
    resolved: ResolvedModel | None, tokens_in: int, tokens_out: int
) -> float | None:
    """Estimate cost from per-token pricing stored in the model record."""
    pricing = (resolved.pricing if resolved else None) or None
    if not pricing:
        return None
    prompt = pricing.get("prompt", 0.0)
    completion = pricing.get("completion", 0.0)
    request = pricing.get("request", 0.0)
    return tokens_in * prompt + tokens_out * completion + request


def _resolve_cost(
    resolved: ResolvedModel | None,
    data_or_usage: dict[str, Any] | None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> tuple[float, bool]:
    """Return (cost_usd, price_known) for a completed request.

    Free models always cost $0 (price_known=True). Otherwise priority:
    provider-reported `usage.cost` -> computed from per-token pricing in
    the model record -> unknown (0.0, price_known=False).
    """
    if resolved and resolved.is_free:
        return 0.0, True
    usage = data_or_usage.get("usage") if isinstance(data_or_usage, dict) else None
    provider_cost = _cost_from_usage(usage)
    if provider_cost is not None:
        return provider_cost, True
    computed = _compute_cost_from_pricing(resolved, tokens_in, tokens_out)
    if computed is not None:
        return computed, True
    return 0.0, False


def _is_free_model(resolved: ResolvedModel | None) -> bool:
    return bool(resolved and resolved.is_free)


def _is_unlimited_model(resolved: ResolvedModel | None) -> bool:
    """Free model with no disclosed limits (requests/min/day or per-request caps)."""
    return bool(resolved and resolved.is_free and not resolved.limits)


def _to_provider(resolved: ResolvedModel, api_key: str | None = None) -> Provider:
    return Provider(
        id=resolved.provider_id,
        name=resolved.provider_name,
        base_url=resolved.base_url,
        api_key=api_key or resolved.api_key,
        protocol=resolved.protocol,
    )


async def _do_request(
    resolved: ResolvedModel,
    protocol: str,
    target: str,
    body: dict[str, Any],
    request_id: str,
    attempt: int = 0,
    path_override: str | None = None,
    request_timeout: float | None = None,
) -> tuple[dict[str, Any], float]:
    pool = get_pool()
    manager = get_manager()
    key = manager.pick_key(resolved.provider_id, attempt)
    provider = _to_provider(resolved, key)
    path = path_override or _provider_path(target, resolved.internal_model)
    start = time.monotonic()
    resp = await pool.request(
        provider=provider,
        path=path,
        method="POST",
        json_body=body,
        request_id=request_id,
        request_timeout=request_timeout,
    )
    latency = time.monotonic() - start
    if resp.status_code >= 400:
        body_text = resp.text[:2000]
        decision = classify(resp.status_code, body_text)
        await resp.aclose()
        if decision.rotate_key or resp.status_code == 429:
            keys = manager.active_keys(resolved.provider_id)
            if len(keys) > 1 and attempt < len(keys) - 1:
                if resp.status_code == 429 and key:
                    manager.mark_key_rate_limited(resolved.provider_id, key, 5.0)
                logger.info(
                    "dispatch.retry_next_key",
                    provider=resolved.provider_name,
                    attempt=attempt + 1,
                    category=decision.category,
                )
                return await _do_request(
                    resolved, protocol, target, body, request_id,
                    attempt=attempt + 1, path_override=path_override, request_timeout=request_timeout,
                )
        raise UpstreamError(
            status_code=resp.status_code,
            message=f"Upstream error ({decision.category})",
            detail=body_text[:300],
            request_id=request_id,
        )
    data = resp.json()
    await resp.aclose()
    return data, latency


async def chat_completion(
    *,
    request_id: str,
    key_hash: str,
    agent_type: str,
    protocol: str,
    model: str,
    body: dict[str, Any],
    marker: CacheMarker | None = None,
) -> dict[str, Any]:
    manager = get_manager()
    resolved = manager.resolve(model, key_hash)
    if resolved is None:
        raise NotFoundError(message=f"Model not found: {model}", request_id=request_id)

    # Image-generation models cannot answer chat completions — auto-route
    # to the provider's images/generations endpoint with the last user text.
    if resolved.kind == "image":
        img_body: dict[str, Any] = {"model": model, "prompt": _extract_prompt(body.get("messages") or [])}
        for k in ("n", "size", "quality", "style", "response_format"):
            if body.get(k) is not None:
                img_body[k] = body[k]
        return await image_generation(
            request_id=request_id,
            key_hash=key_hash,
            agent_type=agent_type,
            model=model,
            body=img_body,
        )

    prompt_text = _extract_prompt(body.get("messages") or [])
    guardrail = get_guardrail()
    guardrail.validate_input(prompt_text)

    tools = body.get("tools")
    temperature = body.get("temperature")
    cacheable = temperature in (None, 0, 0.0) and not body.get("stream")
    cache = get_cache()
    if cacheable:
        cached = await cache.get(model, prompt_text, temperature, tools, key_hash)
        if cached is not None:
            logger.info("dispatch.cache_hit", model=model, request_id=request_id)
            if marker is not None:
                marker.hit = True
            await _record_db_usage(
                agent_type=agent_type,
                provider_id=resolved.provider_id,
                model_id=resolved.model_id,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                is_free=_is_free_model(resolved),
                unlimited=_is_unlimited_model(resolved),
                price_known=bool(resolved and resolved.pricing),
                cache_hit=True,
            )
            return cast(dict[str, Any], json.loads(cached))

    target = normalize_protocol(resolved.protocol)
    translated = translate_request(protocol, target, body, resolved.internal_model)
    data, latency = await _do_request(resolved, protocol, target, translated, request_id)

    output = translate_response(target, protocol, data)
    choice_content = (output.get("choices") or [{}])[0].get("message", {}).get("content")
    guardrail.validate_output(_extract_prompt([{"role": "assistant", "content": choice_content}]))

    if cacheable:
        await cache.set(model, prompt_text, temperature, tools, json.dumps(output, ensure_ascii=False), key_hash)

    tokens_in, tokens_out = _tokens_from(data, target)
    cost, price_known = _resolve_cost(resolved, data, tokens_in, tokens_out)
    is_free = _is_free_model(resolved) or (cost <= 0.000001 and price_known)
    record_usage(tokens_in, tokens_out, cost, provider_id=resolved.provider_id, agent_type=agent_type)
    record_latency(latency, provider_id=resolved.provider_id)
    await _record_db_usage(
        agent_type=agent_type,
        provider_id=resolved.provider_id,
        model_id=resolved.model_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost,
        is_free=is_free,
        unlimited=_is_unlimited_model(resolved),
        price_known=price_known,
        cache_hit=False,
    )
    logger.info(
        "dispatch.completed",
        model=model,
        provider=resolved.provider_name,
        latency_ms=round(latency * 1000, 1),
        cost=round(cost, 8),
        price_known=price_known,
        request_id=request_id,
    )
    return output


async def _record_db_usage(
    *,
    agent_type: str,
    provider_id: str | None,
    model_id: str | None,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    is_free: bool,
    unlimited: bool = False,
    price_known: bool,
    cache_hit: bool,
) -> None:
    """Persist usage with retry on SQLite lock contention.

    Concurrent writes (16+ harness workers) can transiently hit
    'database is locked'; retry a few times with short backoff so usage
    rows are not silently dropped.
    """
    import asyncio

    from sqlalchemy.exc import OperationalError

    attempt = 0
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await get_finops().record_usage(
                    session,
                    agent_type=agent_type,
                    provider_id=provider_id,
                    model_id=model_id,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    is_free=is_free,
                    unlimited=unlimited,
                    price_known=price_known,
                    cache_hit=cache_hit,
                )
            return
        except OperationalError as exc:
            if "locked" not in str(exc).lower():
                logger.exception("dispatch.db_usage_error", agent_type=agent_type)
                return
            attempt += 1
            if attempt > 3:
                logger.warning(
                    "dispatch.db_usage_retry_exhausted",
                    agent_type=agent_type,
                    attempts=attempt,
                )
                return
            await asyncio.sleep(0.05 * attempt)
        except Exception:
            logger.exception("dispatch.db_usage_error", agent_type=agent_type)
            return


async def resolve_stream_cache(
    model: str, key_hash: str, body: dict[str, Any]
) -> tuple[bool, str | None]:
    """Check whether this streaming request can be served from cache.

    Returns (hit, sse_text). Resolves the model and computes the prompt the
    same way chat_completion_stream does, so the route can set the
    X-DM-Cache header before constructing the StreamingResponse.
    """
    manager = get_manager()
    resolved = manager.resolve(model, key_hash)
    if resolved is None:
        return False, None
    prompt_text = _extract_prompt(body.get("messages") or [])
    temperature = body.get("temperature")
    if temperature not in (None, 0, 0.0):
        return False, None
    cache = get_cache()
    tools = body.get("tools")
    cached_sse = await cache.get_stream(model, prompt_text, temperature, tools, key_hash)
    if cached_sse is not None:
        logger.info("dispatch.stream_cache_hit", model=model)
        return True, cached_sse
    return False, None


async def _extract_stream_usage(sse_chunks: list[bytes]) -> dict[str, Any] | None:
    """Extract usage from the final SSE chunk (stream_options.include_usage)."""
    text = b"".join(sse_chunks).decode("utf-8", errors="replace")
    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed.startswith("data:"):
            continue
        data = trimmed[5:].strip()
        if data == "[DONE]":
            continue
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            continue
        usage = parsed.get("usage")
        if isinstance(usage, dict):
            return usage
    return None


async def _record_stream_db_usage(
    *, agent_type: str, provider_id: str | None, resolved: ResolvedModel | None, sse_chunks: list[bytes]
) -> None:
    usage = await _extract_stream_usage(sse_chunks) if sse_chunks else None
    tokens_in = int((usage or {}).get("prompt_tokens", 0) or 0)
    tokens_out = int((usage or {}).get("completion_tokens", 0) or 0)
    lookup: dict[str, Any] = {"usage": usage} if usage else {}
    cost, price_known = _resolve_cost(resolved, lookup, tokens_in, tokens_out)
    is_free = _is_free_model(resolved) or (cost <= 0.000001 and price_known)
    record_usage(tokens_in, tokens_out, cost, provider_id=provider_id, agent_type=agent_type)
    await _record_db_usage(
        agent_type=agent_type,
        provider_id=provider_id,
        model_id=resolved.model_id if resolved else None,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost,
        is_free=is_free,
        unlimited=_is_unlimited_model(resolved),
        price_known=price_known,
        cache_hit=False,
    )


async def chat_completion_stream(
    *,
    request_id: str,
    key_hash: str,
    agent_type: str,
    protocol: str,
    model: str,
    body: dict[str, Any],
) -> AsyncIterator[bytes]:
    manager = get_manager()
    resolved = manager.resolve(model, key_hash)
    if resolved is None:
        raise NotFoundError(message=f"Model not found: {model}", request_id=request_id)

    prompt_text = _extract_prompt(body.get("messages") or [])
    tools = body.get("tools")
    temperature = body.get("temperature")
    cacheable = temperature in (None, 0, 0.0)
    cache = get_cache()
    if cacheable:
        cached_sse = await cache.get_stream(model, prompt_text, temperature, tools, key_hash)
        if cached_sse is not None:
            logger.info("dispatch.stream_cache_hit", model=model, request_id=request_id)
            await _record_db_usage(
                agent_type=agent_type,
                provider_id=resolved.provider_id,
                model_id=resolved.model_id,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                is_free=_is_free_model(resolved),
                unlimited=_is_unlimited_model(resolved),
                price_known=bool(resolved and resolved.pricing),
                cache_hit=True,
            )
            yield cached_sse.encode("utf-8")
            return

    target = normalize_protocol(resolved.protocol)
    translated = translate_request(protocol, target, body, resolved.internal_model)
    pool = get_pool()
    manager = get_manager()
    key = manager.pick_key(resolved.provider_id)
    provider = _to_provider(resolved, key)
    path = _provider_path(target, resolved.internal_model)
    start = time.monotonic()
    resp = await pool.request_stream(
        provider=provider,
        path=path,
        method="POST",
        json_body=translated,
        request_id=request_id,
    )
    if resp.status_code >= 400:
        body_text = resp.text[:2000]
        await resp.aclose()
        raise UpstreamError(
            status_code=resp.status_code,
            message="Upstream provider error",
            detail=body_text[:300],
            request_id=request_id,
        )
    sse_chunks: list[bytes] = []
    try:
        async for chunk in resp.aiter_bytes():
            sse_chunks.append(chunk)
            yield chunk
    finally:
        await resp.aclose()
        if cacheable and sse_chunks:
            full_sse = b"".join(sse_chunks).decode("utf-8", errors="replace")
            await cache.set_stream(model, prompt_text, temperature, tools, full_sse, key_hash)
            logger.info("dispatch.stream_cached", model=model, request_id=request_id)
        record_latency(time.monotonic() - start, provider_id=resolved.provider_id)
        await _record_stream_db_usage(
            agent_type=agent_type,
            provider_id=resolved.provider_id,
            resolved=resolved,
            sse_chunks=sse_chunks,
        )
        logger.info("dispatch.stream_done", model=model, request_id=request_id)


async def image_generation(
    *,
    request_id: str,
    key_hash: str,
    agent_type: str,
    model: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Generate an image via the provider's images/generations endpoint.

    Same-protocol passthrough (openai→openai) — no translation needed.
    """
    manager = get_manager()
    resolved = manager.resolve(model, key_hash)
    if resolved is None:
        raise NotFoundError(message=f"Model not found: {model}", request_id=request_id)
    data, latency = await _do_request(
        resolved, resolved.protocol, resolved.protocol, body, request_id,
        path_override="images/generations", request_timeout=120.0,
    )
    await _record_db_usage(
        agent_type=agent_type,
        provider_id=resolved.provider_id,
        model_id=resolved.model_id,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        is_free=_is_free_model(resolved),
        unlimited=_is_unlimited_model(resolved),
        price_known=bool(resolved and resolved.pricing),
        cache_hit=False,
    )
    logger.info(
        "dispatch.image_generated",
        model=model,
        provider=resolved.provider_name,
        latency_ms=round(latency * 1000, 1),
        request_id=request_id,
    )
    return data


__all__ = [
    "chat_completion",
    "chat_completion_stream",
    "image_generation",
    "resolve_stream_cache",
    "CacheMarker",
]
