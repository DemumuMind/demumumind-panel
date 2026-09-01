"""ProviderManager — in-memory registry of providers/models/keys.

SSOT is the DB; this class is a read-through cache refreshed on demand
(initial load, hot_reload events, and after every insert). Resolution
order for a model: per-key model_mapping override -> global table.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.models import AgentUsage, ApiKey, Model, Provider, ProviderKey
from app.schemas import CreateModelRequest, CreateProviderRequest, PaginatedResponse, UpdateProviderRequest

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

    @property
    def pricing(self) -> dict[str, float] | None:
        """Per-token pricing from model metadata: {prompt, completion, request}."""
        raw = (self.metadata or {}).get("pricing")
        if not isinstance(raw, dict):
            return None
        out: dict[str, float] = {}
        for key in ("prompt", "completion", "request"):
            val = raw.get(key)
            if isinstance(val, (int | float)) and not isinstance(val, bool):
                out[key] = float(val)
        return out or None

    @property
    def is_free(self) -> bool:
        return bool((self.metadata or {}).get("free"))


@dataclass
class ResolvedModel:
    user_model_id: str
    internal_model: str
    provider_id: str
    provider_name: str
    base_url: str
    protocol: str
    api_key: str | None
    model_id: str | None = None
    pricing: dict[str, float] | None = None
    is_free: bool = False


class ProviderManager:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderRecord] = {}
        self._models: dict[str, ModelRecord] = {}
        self._key_mappings: dict[str, dict[str, str]] = {}
        self._provider_keys: dict[str, list[str]] = {}
        self._rr_counter: dict[str, int] = {}
        self._key_cooldown: dict[str, float] = {}
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
        """All active keys for a provider: primary first, then pool keys."""
        pool = self._provider_keys.get(provider_id, [])
        provider = self._provider(provider_id)
        if provider and provider.api_key:
            return [provider.api_key, *pool]
        return pool

    def pick_key(self, provider_id: str, offset: int = 0) -> str | None:
        """Round-robin key selection with rate-limit cooldown.

        Skips keys currently cooling down from a recent 429, so the pool
        spreads load across keys and avoids hammering a rate-limited one.
        offset is used for retry (next key).
        """
        keys = self.active_keys(provider_id)
        if not keys:
            provider = self._provider(provider_id)
            return provider.api_key if provider else None
        n = len(keys)
        now = time.monotonic()
        start = (self._rr_counter.get(provider_id, 0) + offset) % n
        for k in range(n):
            idx = (start + k) % n
            key = keys[idx]
            if self._key_cooldown.get(key, 0.0) <= now:
                self._rr_counter[provider_id] = (idx + 1) % n
                return key
        # all keys cooling down — fall back to plain round-robin
        idx = (self._rr_counter.get(provider_id, 0) + offset) % n
        self._rr_counter[provider_id] = (idx + 1) % n
        return keys[idx]

    def mark_key_rate_limited(self, provider_id: str, api_key: str, cooldown_seconds: float = 5.0) -> None:
        """Temporarily deprioritize a key after a rate-limit (429) response."""
        self._key_cooldown[api_key] = time.monotonic() + cooldown_seconds
        logger.info("provider_manager.key_cooldown", provider=provider_id, cooldown_s=cooldown_seconds)

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
            model_id=record.id,
            pricing=record.pricing,
            is_free=record.is_free,
        )

    async def list_available_models_detailed(
        self, limit: int, offset: int, provider_id: str | None = None, provider_name: str | None = None
    ) -> PaginatedResponse[dict[str, Any]]:
        all_models = [m for m in self._models.values() if m.is_active]
        if provider_id:
            all_models = [m for m in all_models if m.provider_id == provider_id]
        if provider_name:
            matched: list[ModelRecord] = []
            for m in all_models:
                prov = self._provider(m.provider_id)
                if prov is not None and prov.name == provider_name:
                    matched.append(m)
            all_models = matched
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

    async def update_provider(self, session: AsyncSession, provider: Provider, data: UpdateProviderRequest) -> Provider:
        changes = data.model_dump(exclude_unset=True)
        if changes.get("is_default"):
            await session.execute(update(Provider).values(is_default=0))
        if "metadata" in changes:
            provider.meta = json.dumps(changes.pop("metadata") or {})
        for key, value in changes.items():
            if key == "is_default":
                provider.is_default = 1 if value else 0
            elif key == "is_active":
                provider.is_active = 1 if value else 0
            else:
                setattr(provider, key, value)
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

    async def update_model_pricing(self, session: AsyncSession, model: Model, data: dict[str, Any]) -> Model:
        """Merge pricing/free/limits into model.meta with source='manual'."""
        mmeta = json.loads(model.meta or "{}")
        pricing = mmeta.get("pricing", {}) or {}
        if not isinstance(pricing, dict):
            pricing = {}
        changed = False
        if "price_prompt_per_token" in data:
            pricing["prompt"] = data["price_prompt_per_token"]
            changed = True
        if "price_completion_per_token" in data:
            pricing["completion"] = data["price_completion_per_token"]
            changed = True
        if "price_request" in data:
            pricing["request"] = data["price_request"]
            changed = True
        if "free" in data:
            mmeta["free"] = bool(data["free"])
            changed = True
        if "limit_requests_per_minute" in data and data["limit_requests_per_minute"] is not None:
            limits = mmeta.get("limits", {}) or {}
            limits["requests_per_minute"] = data["limit_requests_per_minute"]
            mmeta["limits"] = limits
            changed = True
        if "limit_requests_per_day" in data and data["limit_requests_per_day"] is not None:
            limits = mmeta.get("limits", {}) or {}
            limits["requests_per_day"] = data["limit_requests_per_day"]
            mmeta["limits"] = limits
            changed = True
        if changed:
            mmeta["pricing"] = pricing
            mmeta["price_source"] = "manual"
            model.meta = json.dumps(mmeta)
            await session.commit()
            await session.refresh(model)
            await self.refresh()
            await self._reconcile_usage_by_model(session, model, pricing, mmeta.get("free", False))
        return model

    async def _reconcile_usage_by_model(
        self, session: AsyncSession, model: Model, pricing: dict[str, float], is_free: bool
    ) -> None:
        """Recompute cost_usd/is_free/price_known for all usage rows of this model."""
        p = pricing.get("prompt", 0.0) if pricing else 0.0
        c = pricing.get("completion", 0.0) if pricing else 0.0
        r = pricing.get("request", 0.0) if pricing else 0.0
        has_pricing = bool(pricing)
        rows = await session.execute(
            select(AgentUsage).where(
                AgentUsage.model_id == model.id,
                AgentUsage.price_known == 0,
            )
        )
        for row in rows.scalars().all():
            if has_pricing:
                row.cost_usd = row.tokens_in * p + row.tokens_out * c + r
                row.price_known = 1
            else:
                row.cost_usd = 0.0
                row.price_known = 0
            row.is_free = 1 if is_free else 0
        await session.commit()


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
