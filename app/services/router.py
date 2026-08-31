"""Model router — resolves user_model_id -> (provider, internal_model).

Resolution order: per-key model_mapping override -> global table.
Pagination via ProviderManager.list_available_models_detailed.
"""

from __future__ import annotations

from typing import Any

from app.schemas import PaginatedResponse
from app.services.provider_manager import ProviderManager, ResolvedModel, get_manager


class Router:
    def __init__(self, manager: ProviderManager) -> None:
        self._manager = manager

    async def resolve(self, user_model_id: str, key_hash: str | None = None) -> ResolvedModel | None:
        return self._manager.resolve(user_model_id, key_hash)

    async def list_models_detailed(self, limit: int, offset: int) -> PaginatedResponse[dict[str, Any]]:
        return await self._manager.list_available_models_detailed(limit, offset)

    @property
    def manager(self) -> ProviderManager:
        return self._manager


_router: Router | None = None


def get_router() -> Router:
    global _router
    if _router is None:
        _router = Router(get_manager())
    return _router


__all__ = ["Router", "get_router"]
