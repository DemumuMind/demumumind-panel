"""Public API routes — OpenAI/Anthropic/Gemini-compatible gateways + paginated listings.

Every response carries X-Request-ID (middleware). Rate limit on the chat
endpoint. Auth: client keys (hmac) for /v1/*, panel key for admin.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import text

from app.api.v1.middleware import AuthState, get_agent_type
from app.core.db import AsyncSessionLocal
from app.core.errors import AuthError
from app.core.redis import get_redis
from app.schemas import (
    AnthropicMessageRequest,
    ChatCompletionRequest,
    GeminiGenerateRequest,
    HealthOut,
    ImageGenerationRequest,
    PaginatedResponse,
)
from app.services.agent_id import get_registry
from app.services.dispatch import (
    CacheMarker,
    chat_completion,
    chat_completion_stream,
    image_generation,
    resolve_stream_cache,
)
from app.services.finops import get_finops
from app.services.router import get_router
from app.services.telemetry import generate_metrics
from app.version import VERSION

logger = structlog.get_logger(__name__)

limiter = Limiter(key_func=get_remote_address)

root_router = APIRouter(tags=["root"])
v1_router = APIRouter(prefix="/v1", tags=["v1"])

PANEL_SENTINEL = "__panel__"


def _drop_nulls(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively remove keys with None values (strict providers reject null)."""
    result: dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            cleaned = _drop_nulls(v)
            if cleaned:
                result[k] = cleaned
        elif isinstance(v, list):
            cleaned_list: list[Any] = []
            for item in v:
                if isinstance(item, dict):
                    cleaned_item = _drop_nulls(item)
                    if cleaned_item:
                        cleaned_list.append(cleaned_item)
                elif item is not None:
                    cleaned_list.append(item)
            if cleaned_list:
                result[k] = cleaned_list
        else:
            result[k] = v
    return result


async def require_client_key(request: Request) -> str:
    auth = AuthState(request)
    key_hash = await auth.client_key_hash()
    if key_hash is not None:
        return key_hash
    if await auth.is_panel_authorized():
        return PANEL_SENTINEL
    raise AuthError(message="Missing or invalid API key", request_id=getattr(request.state, "request_id", None))


async def require_panel(request: Request) -> None:
    auth = AuthState(request)
    if not await auth.is_panel_authorized():
        raise AuthError(message="Invalid panel key", request_id=getattr(request.state, "request_id", None))


KeyHashDep = Annotated[str, Depends(require_client_key)]


@root_router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    checks: dict[str, str] = {}
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception:
            checks["db"] = "error"
    redis = await get_redis()
    if redis is None:
        checks["redis"] = "fallback"
    else:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "fallback"
    return HealthOut(status="ok", version=VERSION, checks=checks)


@root_router.get("/metrics")
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_metrics(), media_type="text/plain")


@v1_router.post("/chat/completions")
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    key_hash: KeyHashDep,
) -> Any:
    request_id = getattr(request.state, "request_id", "")
    agent_type = get_agent_type(request)
    payload = body.model_dump(exclude_none=False)
    payload = _drop_nulls(payload)
    if body.stream:
        is_cached, cached_sse = await resolve_stream_cache(body.model, key_hash, payload)
        headers = {"X-DM-Cache": "hit"} if is_cached else None
        if is_cached and cached_sse is not None:
            async def _cached_stream() -> AsyncIterator[bytes]:
                yield cached_sse.encode("utf-8")
            return StreamingResponse(_cached_stream(), media_type="text/event-stream", headers=headers)
        stream = chat_completion_stream(
            request_id=request_id,
            key_hash=key_hash,
            agent_type=agent_type,
            protocol="openai",
            model=body.model,
            body=payload,
        )
        return StreamingResponse(stream, media_type="text/event-stream", headers=headers)
    marker = CacheMarker()
    result = await chat_completion(
        request_id=request_id,
        key_hash=key_hash,
        agent_type=agent_type,
        protocol="openai",
        model=body.model,
        body=payload,
        marker=marker,
    )
    resp_headers = {"X-DM-Cache": "hit"} if marker.hit else None
    return JSONResponse(result, headers=resp_headers)


@v1_router.post("/images/generations")
async def images_generations(
    request: Request,
    body: ImageGenerationRequest,
    key_hash: KeyHashDep,
) -> Any:
    request_id = getattr(request.state, "request_id", "")
    agent_type = get_agent_type(request)
    payload = body.model_dump(exclude_none=False)
    payload = _drop_nulls(payload)
    result = await image_generation(
        request_id=request_id,
        key_hash=key_hash,
        agent_type=agent_type,
        model=body.model,
        body=payload,
    )
    return JSONResponse(result)


@v1_router.post("/messages")
async def anthropic_messages(
    request: Request,
    body: AnthropicMessageRequest,
    key_hash: KeyHashDep,
) -> Any:
    request_id = getattr(request.state, "request_id", "")
    agent_type = get_agent_type(request)
    payload = body.model_dump(exclude_none=False)
    payload = _drop_nulls(payload)
    marker = CacheMarker()
    result = await chat_completion(
        request_id=request_id,
        key_hash=key_hash,
        agent_type=agent_type,
        protocol="anthropic",
        model=body.model,
        body=payload,
        marker=marker,
    )
    resp_headers = {"X-DM-Cache": "hit"} if marker.hit else None
    return JSONResponse(result, headers=resp_headers)


@v1_router.post("/v1beta/models/{model}:generateContent")
async def gemini_generate_content(
    model: str,
    request: Request,
    body: GeminiGenerateRequest,
    key_hash: KeyHashDep,
) -> Any:
    request_id = getattr(request.state, "request_id", "")
    agent_type = get_agent_type(request)
    payload = body.model_dump(exclude_none=False)
    payload = _drop_nulls(payload)
    payload["model"] = model
    marker = CacheMarker()
    result = await chat_completion(
        request_id=request_id,
        key_hash=key_hash,
        agent_type=agent_type,
        protocol="gemini",
        model=model,
        body=payload,
        marker=marker,
    )
    resp_headers = {"X-DM-Cache": "hit"} if marker.hit else None
    return JSONResponse(result, headers=resp_headers)


@v1_router.get("/models")
async def list_models(
    key_hash: KeyHashDep,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    provider: str | None = Query(default=None),
) -> PaginatedResponse[dict[str, Any]]:
    return await get_router().list_models_detailed(limit, offset, provider)


@v1_router.get("/agents")
async def list_agents(
    key_hash: KeyHashDep,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[Any]:
    async with AsyncSessionLocal() as session:
        return await get_registry().stats(session, limit, offset)


@v1_router.get("/usage")
async def list_usage(
    key_hash: KeyHashDep,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[Any]:
    async with AsyncSessionLocal() as session:
        return await get_finops().usage_stats(session, limit, offset)


@v1_router.get("/usage/timeseries")
async def usage_timeseries(
    key_hash: KeyHashDep,
    days: int = Query(default=30, ge=1, le=365),
) -> list[Any]:
    async with AsyncSessionLocal() as session:
        return await get_finops().usage_timeseries(session, days)


@v1_router.get("/usage/by-provider")
async def usage_by_provider(
    key_hash: KeyHashDep,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[Any]:
    async with AsyncSessionLocal() as session:
        return await get_finops().usage_by_provider(session, limit, offset)


__all__ = ["root_router", "v1_router", "limiter"]
