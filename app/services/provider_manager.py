"""ProviderManager — in-memory registry of providers/models/keys.

SSOT is the DB; this class is a read-through cache refreshed on demand
(initial load, hot_reload events, and after every insert). Resolution
order for a model: per-key model_mapping override -> global table.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.models import ApiKey, Model, Provider, ProviderKey
from app.schemas import CreateModelRequest, CreateProviderRequest, PaginatedResponse

logger = structlog.get_logger(__name__)


@dataclass
class ProviderRecord:
    id: str
    name: str
    base_url: str
    api_key: str | None
    protocol: str
    is_default: bool
    is_active: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_orm(cls, p: Provider) -> ProviderRecord:
        meta = json.loads(p.meta or "{}")
        return cls(
            id=p.id,
            name=p.name,
            base_url=p.base_url,
            api_key=p.api_key,
            protocol=p.protocol,
            is_default=bool(p.is_default),
            is_active=bool(p.is_active),
            metadata=meta if isinstance(meta, dict) else {},
        )


@dataclass
class ModelRecord:
    id: str
    provider_id: str
    user_model_id: str
    internal_model: str
    is_active: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_orm(cls, m: Model) -> ModelRecord:
        meta = json.loads(m.meta or "{}")
        return cls(
            id=m.id,
            provider_id=m.provider_id,
            user_model_id=m.user_model_id,
            internal_model=m.internal_model,
            is_active=bool(m.is_active),
            metadata=meta if isinstance(meta, dict) else {},
        )


@dataclass
class ResolvedModel:
    user_model_id: str
    internal_model: str
    provider_id: str
    provider_name: str
    base_url: str
    protocol: str
    api_key: str | None


class ProviderManager:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderRecord] = {}
        self._models: dict[str, ModelRecord] = {}
        self._key_mappings: dict[str, dict[str, str]] = {}
        self._provider_keys: dict[str, list[str]] = {}
        self._rr_counter: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def load(self, session: AsyncSession) -> None:
        await self._reload(session)

    async def refresh(self) -> None:
        async with self._lock, AsyncSessionLocal() as session:
            await self._reload(session)
        logger.info(
            "provider_manager.refresh_done",
            providers=len(self._providers),
            models=len(self._models),
        )

    async def _reload(self, session: AsyncSession) -> None:
        providers = (await session.execute(select(Provider))).scalars().all()
        models = (await session.execute(select(Model))).scalars().all()
        keys = (await session.execute(select(ApiKey.key_hash, ApiKey.model_mapping))).all()
        pool_keys = (await session.execute(select(ProviderKey).where(ProviderKey.is_active == 1))).scalars().all()
        self._providers = {p.id: ProviderRecord.from_orm(p) for p in providers}
        self._models = {m.user_model_id: ModelRecord.from_orm(m) for m in models}
        self._key_mappings = {}
        for kh, raw in keys:
            mapping = json.loads(raw or "{}")
            if isinstance(mapping, dict):
                self._key_mappings[kh] = {str(k): str(v) for k, v in mapping.items()}
        self._provider_keys = {}
        for pk in pool_keys:
            self._provider_keys.setdefault(pk.provider_id, []).append(pk.api_key)

    def _provider(self, provider_id: str) -> ProviderRecord | None:
        return self._providers.get(provider_id)

    def active_keys(self, provider_id: str) -> list[str]:
        return self._provider_keys.get(provider_id, [])

    def pick_key(self, provider_id: str, offset: int = 0) -> str | None:
        """Round-robin key selection. offset is used for retry (next key)."""
        keys = self.active_keys(provider_id)
        if not keys:
            provider = self._provider(provider_id)
            return provider.api_key if provider else None
        idx = (self._rr_counter.get(provider_id, 0) + offset) % len(keys)
        self._rr_counter[provider_id] = (idx + 1) % len(keys)
        return keys[idx]

    def resolve(self, user_model_id: str, key_hash: str | None = None) -> ResolvedModel | None:
        target = user_model_id
        if key_hash and key_hash in self._key_mappings and user_model_id in self._key_mappings[key_hash]:
            target = self._key_mappings[key_hash][user_model_id]
        record = self._models.get(target)
        if record is None or not record.is_active:
            return None
        provider = self._provider(record.provider_id)
        if provider is None or not provider.is_active:
            return None
        return ResolvedModel(
            user_model_id=target,
            internal_model=record.internal_model,
            provider_id=provider.id,
            provider_name=provider.name,
            base_url=provider.base_url,
            protocol=provider.protocol,
            api_key=provider.api_key,
        )

    async def list_available_models_detailed(
        self, limit: int, offset: int
    ) -> PaginatedResponse[dict[str, Any]]:
        all_models = [m for m in self._models.values() if m.is_active]
        total = len(all_models)
        page = all_models[offset : offset + limit]
        items: list[dict[str, Any]] = []
        for m in page:
            provider = self._provider(m.provider_id)
            items.append(
                {
                    "id": m.id,
                    "user_model_id": m.user_model_id,
                    "internal_model": m.internal_model,
                    "is_active": m.is_active,
                    "metadata": m.metadata,
                    "provider": {
                        "id": provider.id if provider else None,
                        "name": provider.name if provider else None,
                        "protocol": provider.protocol if provider else None,
                    },
                }
            )
        return PaginatedResponse[dict[str, Any]](items=items, total=total, limit=limit, offset=offset)

    async def insert_provider(self, session: AsyncSession, data: CreateProviderRequest) -> Provider:
        if data.is_default:
            await session.execute(update(Provider).values(is_default=0))
        provider = Provider(
            name=data.name,
            base_url=data.base_url,
            api_key=data.api_key,
            protocol=data.protocol,
            is_default=1 if data.is_default else 0,
            is_active=1 if data.is_active else 0,
            meta=json.dumps(data.metadata or {}),
        )
        session.add(provider)
        await session.commit()
        await session.refresh(provider)
        await self.refresh()
        return provider

    async def insert_model(self, session: AsyncSession, data: CreateModelRequest) -> Model:
        model = Model(
            provider_id=data.provider_id,
            user_model_id=data.user_model_id,
            internal_model=data.internal_model,
            meta=json.dumps(data.metadata or {}),
            is_active=1 if data.is_active else 0,
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        await self.refresh()
        return model


_manager: ProviderManager | None = None


def get_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager


__all__ = [
    "ProviderManager",
    "ProviderRecord",
    "ModelRecord",
    "ResolvedModel",
    "get_manager",
]
