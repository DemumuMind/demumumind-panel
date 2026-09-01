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
) -> tuple[dict[str, Any], float]:
    pool = get_pool()
    manager = get_manager()
    key = manager.pick_key(resolved.provider_id, attempt)
    provider = _to_provider(resolved, key)
    path = _provider_path(target, resolved.internal_model)
    start = time.monotonic()
    resp = await pool.request(
        provider=provider,
        path=path,
        method="POST",
        json_body=body,
        request_id=request_id,
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
                return await _do_request(resolved, protocol, target, body, request_id, attempt=attempt + 1)
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
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
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
    record_usage(tokens_in, tokens_out, 0.0, provider_id=resolved.provider_id, agent_type=agent_type)
    record_latency(latency, provider_id=resolved.provider_id)
    await _record_db_usage(
        agent_type=agent_type,
        provider_id=resolved.provider_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=0.0,
    )
    logger.info(
        "dispatch.completed",
        model=model,
        provider=resolved.provider_name,
        latency_ms=round(latency * 1000, 1),
        request_id=request_id,
    )
    return output


async def _record_db_usage(
    *, agent_type: str, provider_id: str | None, tokens_in: int, tokens_out: int, cost_usd: float
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            await get_finops().record_usage(
                session,
                agent_type=agent_type,
                provider_id=provider_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
            )
    except Exception:
        logger.exception("dispatch.db_usage_error", agent_type=agent_type)


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
    *, agent_type: str, provider_id: str | None, sse_chunks: list[bytes]
) -> None:
    usage = await _extract_stream_usage(sse_chunks) if sse_chunks else None
    tokens_in = int((usage or {}).get("prompt_tokens", 0) or 0)
    tokens_out = int((usage or {}).get("completion_tokens", 0) or 0)
    record_usage(tokens_in, tokens_out, 0.0, provider_id=provider_id, agent_type=agent_type)
    await _record_db_usage(
        agent_type=agent_type,
        provider_id=provider_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=0.0,
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
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
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
            sse_chunks=sse_chunks,
        )
        logger.info("dispatch.stream_done", model=model, request_id=request_id)


__all__ = [
    "chat_completion",
    "chat_completion_stream",
    "resolve_stream_cache",
    "CacheMarker",
]
