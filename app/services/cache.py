"""In-memory LLM response cache with hmac-salted keying.

Key = user_model_id + hmac_sha256(prompt, PANEL_API_KEY) + temperature + sha256(tools_json).
Never logs prompt. asyncio.Lock for set/evict. LRU-style eviction when over max_entries.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections import OrderedDict
from typing import Any

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class CacheService:
    def __init__(self, max_entries: int = 4096) -> None:
        self._store: OrderedDict[str, str] = OrderedDict()
        self._lock = asyncio.Lock()
        self._max_entries = max_entries

    def _key(self, user_model_id: str, prompt: str, temperature: float | None, tools: list[Any] | None) -> str:
        salt = settings.PANEL_API_KEY.encode()
        prompt_hmac = hmac.new(salt, prompt.encode(), hashlib.sha256).hexdigest()[:32]
        tools_json = json.dumps(tools, sort_keys=True) if tools else ""
        tools_hash = hashlib.sha256(tools_json.encode()).hexdigest()[:16]
        temp_str = f"{temperature:.4f}" if temperature is not None else "none"
        raw = f"{user_model_id}:{prompt_hmac}:{temp_str}:{tools_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(
        self, user_model_id: str, prompt: str, temperature: float | None, tools: list[Any] | None
    ) -> str | None:
        key = self._key(user_model_id, prompt, temperature, tools)
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                return self._store[key]
        return None

    async def set(
        self,
        user_model_id: str,
        prompt: str,
        temperature: float | None,
        tools: list[Any] | None,
        value: str,
    ) -> None:
        key = self._key(user_model_id, prompt, temperature, tools)
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            else:
                if len(self._store) >= self._max_entries:
                    evicted_key, _ = self._store.popitem(last=False)
                    logger.debug("cache.evicted", key_prefix=evicted_key[:8])
            self._store[key] = value

    async def invalidate(self, pattern: str) -> int:
        count = 0
        async with self._lock:
            to_delete = [k for k in self._store if pattern in k]
            for k in to_delete:
                del self._store[k]
                count += 1
        if count:
            logger.info("cache.invalidated", pattern=pattern, count=count)
        return count


_cache: CacheService | None = None


def get_cache() -> CacheService:
    global _cache
    if _cache is None:
        _cache = CacheService()
    return _cache


__all__ = ["CacheService", "get_cache"]