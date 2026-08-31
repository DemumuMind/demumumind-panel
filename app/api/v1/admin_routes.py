"""Admin routes — CRUD providers/models/keys, provider test, plugin upload, seed.

All endpoints require `Authorization: Bearer $PANEL_API_KEY`. Pagination
everywhere. Key POST returns the raw key exactly once.
"""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, File, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.middleware import AuthState, hash_key
from app.config import settings
from app.core.db import get_db
from app.core.errors import AppError, NotFoundError
from app.models import ApiKey, Model, Provider, ProviderKey
from app.schemas import (
    ApiKeyCreated,
    ApiKeyOut,
    CleanupReport,
    CreateApiKeyRequest,
    CreateModelRequest,
    CreateProviderKeyRequest,
    CreateProviderRequest,
    DiscoveredModelStatus,
    LoginRequest,
    ModelDiscoveryResult,
    ModelOut,
    PaginatedResponse,
    PluginOut,
    ProviderKeyOut,
    ProviderOut,
    TestProviderResult,
)
from app.seed import run_seed
from app.services.cleanup import run_cleanup
from app.services.discovery import discover_and_test, test_provider_model
from app.services.plugin_manager import get_plugin_manager
from app.services.pool import get_pool
from app.services.provider_manager import get_manager

logger = structlog.get_logger(__name__)

admin_router = APIRouter(prefix="/v1/admin", tags=["admin"])
auth_router = APIRouter(prefix="/v1/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


async def require_panel(request: Request) -> None:
    auth = AuthState(request)
    if not await auth.is_panel_authorized():
        raise AppError(401, "unauthorized", "Invalid panel key", request_id=getattr(request.state, "request_id", None))


PanelDep = Annotated[None, Depends(require_panel)]


async def _provider_or_404(session: AsyncSession, provider_id: str) -> Provider:
    row = await session.execute(select(Provider).where(Provider.id == provider_id).limit(1))
    provider = row.scalar_one_or_none()
    if provider is None:
        raise NotFoundError(message=f"Provider not found: {provider_id}")
    return provider


async def _model_or_404(session: AsyncSession, model_id: str) -> Model:
    row = await session.execute(select(Model).where(Model.id == model_id).limit(1))
    model = row.scalar_one_or_none()
    if model is None:
        raise NotFoundError(message=f"Model not found: {model_id}")
    return model


@auth_router.post("/login")
async def login(body: LoginRequest, request: Request) -> Response:
    if not hmac.compare_digest(body.panel_api_key, settings.PANEL_API_KEY):
        raise AppError(401, "unauthorized", "Invalid panel key", request_id=getattr(request.state, "request_id", None))
    response = JSONResponse({"ok": True, "request_id": getattr(request.state, "request_id", None)})
    response.set_cookie(
        key="panel_api_key",
        value=body.panel_api_key,
        httponly=True,
        secure=False,
        samesite="strict",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@admin_router.get("/providers")
async def list_providers(
    _: PanelDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[ProviderOut]:
    total = int((await session.execute(select(func.count()).select_from(Provider))).scalar_one() or 0)
    rows = await session.execute(select(Provider).order_by(Provider.created_at).limit(limit).offset(offset))
    items = [ProviderOut.model_validate(p) for p in rows.scalars().all()]
    return PaginatedResponse[ProviderOut](items=items, total=total, limit=limit, offset=offset)


@admin_router.post("/providers", response_model=ProviderOut, status_code=201)
async def create_provider(
    _: PanelDep,
    body: CreateProviderRequest,
    session: SessionDep,
) -> ProviderOut:
    try:
        provider = await get_manager().insert_provider(session, body)
    except IntegrityError:
        raise AppError(409, "duplicate", "Provider name already exists") from None
    return ProviderOut.model_validate(provider)


@admin_router.get("/providers/{provider_id}")
async def get_provider(
    provider_id: str,
    _: PanelDep,
    session: SessionDep,
) -> ProviderOut:
    return ProviderOut.model_validate(await _provider_or_404(session, provider_id))


@admin_router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    _: PanelDep,
    session: SessionDep,
) -> dict[str, bool]:
    provider = await _provider_or_404(session, provider_id)
    await session.delete(provider)
    await session.commit()
    await get_manager().refresh()
    return {"ok": True}


@admin_router.post("/providers/{provider_id}/test")
async def test_provider(
    provider_id: str,
    _: PanelDep,
    session: SessionDep,
    request: Request,
) -> TestProviderResult:
    provider = await _provider_or_404(session, provider_id)
    pool = get_pool()
    try:
        resp = await pool.request(
            provider=provider,
            path="models",
            method="GET",
            json_body=None,
            request_id=getattr(request.state, "request_id", ""),
        )
        if resp.status_code >= 400:
            return TestProviderResult(ok=False, models=[], message=f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        models = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
        return TestProviderResult(ok=True, models=models[:50])
    except Exception as exc:
        logger.warning("admin.provider_test_error", provider=provider_id, error=str(exc))
        return TestProviderResult(ok=False, models=[], message=str(exc)[:200])


@admin_router.post("/providers/{provider_id}/discover", response_model=ModelDiscoveryResult)
async def discover_provider_models_endpoint(
    provider_id: str,
    _: PanelDep,
    session: SessionDep,
    request: Request,
) -> ModelDiscoveryResult:
    provider = await _provider_or_404(session, provider_id)
    return await discover_and_test(provider, session, getattr(request.state, "request_id", ""))


@admin_router.post("/providers/{provider_id}/models/{internal_model}/test", response_model=DiscoveredModelStatus)
async def test_single_model_endpoint(
    provider_id: str,
    internal_model: str,
    _: PanelDep,
    session: SessionDep,
    request: Request,
) -> DiscoveredModelStatus:
    provider = await _provider_or_404(session, provider_id)
    return await test_provider_model(provider, internal_model, getattr(request.state, "request_id", ""))


@admin_router.get("/providers/{provider_id}/keys", response_model=list[ProviderKeyOut])
async def list_provider_keys(
    provider_id: str,
    _: PanelDep,
    session: SessionDep,
) -> list[ProviderKeyOut]:
    provider = await _provider_or_404(session, provider_id)
    rows = await session.execute(
        select(ProviderKey).where(ProviderKey.provider_id == provider_id).order_by(ProviderKey.created_at)
    )
    out: list[ProviderKeyOut] = []
    # primary key (Provider.api_key) is always listed first as "primary"
    if provider.api_key:
        masked = f"{provider.api_key[:6]}…{provider.api_key[-4:]}" if len(provider.api_key) > 12 else "…"
        out.append(
            ProviderKeyOut(
                id="primary",
                provider_id=provider_id,
                api_key_masked=f"{masked} (primary)",
                is_active=bool(provider.is_active),
                last_used_at=None,
                success_count=0,
                fail_count=0,
                created_at=provider.created_at,
            )
        )
    for pk in rows.scalars().all():
        masked = f"{pk.api_key[:6]}…{pk.api_key[-4:]}" if len(pk.api_key) > 12 else "…"
        out.append(
            ProviderKeyOut(
                id=pk.id,
                provider_id=pk.provider_id,
                api_key_masked=masked,
                is_active=bool(pk.is_active),
                last_used_at=pk.last_used_at,
                success_count=pk.success_count,
                fail_count=pk.fail_count,
                created_at=pk.created_at,
            )
        )
    return out


@admin_router.post("/providers/{provider_id}/keys", response_model=ProviderKeyOut, status_code=201)
async def add_provider_key(
    provider_id: str,
    _: PanelDep,
    session: SessionDep,
    body: CreateProviderKeyRequest,
) -> ProviderKeyOut:
    await _provider_or_404(session, provider_id)
    pk = ProviderKey(provider_id=provider_id, api_key=body.api_key)
    session.add(pk)
    await session.commit()
    await session.refresh(pk)
    await get_manager().refresh()
    masked = f"{pk.api_key[:6]}…{pk.api_key[-4:]}" if len(pk.api_key) > 12 else "…"
    logger.info("admin.provider_key_added", provider=provider_id, prefix=body.api_key[:6])
    return ProviderKeyOut(
        id=pk.id,
        provider_id=pk.provider_id,
        api_key_masked=masked,
        is_active=bool(pk.is_active),
        last_used_at=pk.last_used_at,
        success_count=pk.success_count,
        fail_count=pk.fail_count,
        created_at=pk.created_at,
    )


@admin_router.delete("/providers/{provider_id}/keys/{key_id}")
async def delete_provider_key(
    provider_id: str,
    key_id: str,
    _: PanelDep,
    session: SessionDep,
) -> dict[str, bool]:
    await _provider_or_404(session, provider_id)
    row = await session.execute(
        select(ProviderKey).where(ProviderKey.id == key_id, ProviderKey.provider_id == provider_id).limit(1)
    )
    pk = row.scalar_one_or_none()
    if pk is None:
        raise NotFoundError(message=f"Provider key not found: {key_id}")
    await session.delete(pk)
    await session.commit()
    await get_manager().refresh()
    return {"ok": True}


@admin_router.post("/cleanup", response_model=CleanupReport)
async def cleanup_endpoint(_: PanelDep, session: SessionDep) -> CleanupReport:
    return await run_cleanup(session)


@admin_router.get("/models")
async def list_models(
    _: PanelDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[ModelOut]:
    total = int((await session.execute(select(func.count()).select_from(Model))).scalar_one() or 0)
    rows = await session.execute(select(Model).order_by(Model.created_at).limit(limit).offset(offset))
    items = [ModelOut.model_validate(m) for m in rows.scalars().all()]
    return PaginatedResponse[ModelOut](items=items, total=total, limit=limit, offset=offset)


@admin_router.post("/models", response_model=ModelOut, status_code=201)
async def create_model(
    _: PanelDep,
    body: CreateModelRequest,
    session: SessionDep,
) -> ModelOut:
    await _provider_or_404(session, body.provider_id)
    try:
        model = await get_manager().insert_model(session, body)
    except IntegrityError:
        raise AppError(409, "duplicate", "user_model_id already exists") from None
    return ModelOut.model_validate(model)


@admin_router.delete("/models/{model_id}")
async def delete_model(
    model_id: str,
    _: PanelDep,
    session: SessionDep,
) -> dict[str, bool]:
    model = await _model_or_404(session, model_id)
    await session.delete(model)
    await session.commit()
    await get_manager().refresh()
    return {"ok": True}


@admin_router.get("/keys")
async def list_keys(
    _: PanelDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[ApiKeyOut]:
    total = int((await session.execute(select(func.count()).select_from(ApiKey))).scalar_one() or 0)
    rows = await session.execute(select(ApiKey).order_by(ApiKey.created_at).limit(limit).offset(offset))
    items = [ApiKeyOut.model_validate(k) for k in rows.scalars().all()]
    return PaginatedResponse[ApiKeyOut](items=items, total=total, limit=limit, offset=offset)


@admin_router.post("/keys", response_model=ApiKeyCreated, status_code=201)
async def create_key(
    _: PanelDep,
    body: CreateApiKeyRequest,
    session: SessionDep,
) -> ApiKeyCreated:
    import json as _json

    raw_key = f"dm-{uuid.uuid4().hex}"
    key_hash = hash_key(raw_key)
    key = ApiKey(
        key_hash=key_hash,
        group_id=body.group_id,
        model_mapping=_json.dumps(body.model_mapping),
        monthly_budget=body.monthly_budget,
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)
    await get_manager().refresh()
    logger.info("admin.key_created", key_prefix=key_hash[:8])
    return ApiKeyCreated(id=key.id, api_key=raw_key)


@admin_router.delete("/keys/{key_id}")
async def delete_key(
    key_id: str,
    _: PanelDep,
    session: SessionDep,
) -> dict[str, bool]:
    row = await session.execute(select(ApiKey).where(ApiKey.id == key_id).limit(1))
    key = row.scalar_one_or_none()
    if key is None:
        raise NotFoundError(message=f"Key not found: {key_id}")
    await session.delete(key)
    await session.commit()
    await get_manager().refresh()
    return {"ok": True}


@admin_router.post("/plugins/upload", response_model=PluginOut)
async def upload_plugin(
    request: Request,
    _: PanelDep,
    payload: bytes = File(...),
    x_plugin_name: str | None = Header(default=None),
    x_plugin_signature: str | None = Header(default=None),
) -> PluginOut:
    if not x_plugin_name:
        raise AppError(422, "validation_error", "X-Plugin-Name header required")
    runtime = get_plugin_manager()
    ok = await runtime.load(x_plugin_name, payload, x_plugin_signature or "")
    info = next((p for p in runtime.list() if p.name == x_plugin_name), None)
    return PluginOut(
        name=x_plugin_name,
        signature_valid=info.signature_valid if info else False,
        size_bytes=len(payload),
        loaded=ok,
        error=info.error if info else None,
    )


@admin_router.get("/plugins")
async def list_plugins(_: PanelDep) -> list[PluginOut]:
    runtime = get_plugin_manager()
    return [
        PluginOut(
            name=p.name,
            signature_valid=p.signature_valid,
            size_bytes=p.size_bytes,
            loaded=p.loaded,
            error=p.error,
        )
        for p in runtime.list()
    ]


@admin_router.post("/seed")
async def seed(_: PanelDep, session: SessionDep) -> dict[str, Any]:
    return await run_seed(session)


__all__ = ["admin_router", "auth_router"]
