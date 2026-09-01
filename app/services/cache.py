"""In-memory LLM response cache with hmac-salted, per-tenant keying.

Key = key_hash + user_model_id + hmac_sha256(prompt, PANEL_API_KEY) +
temperature + sha256(tools_json). Two slots: plain key for JSON responses
(non-stream) and `stream:`-prefixed for SSE text. TTL applies to both.
Never logs prompt. asyncio.Lock for set/evict. LRU eviction over max_entries.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from collections import OrderedDict
from typing import Any

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

CACHE_TTL_SECONDS = 300


class CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: str, ttl_seconds: int) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl_seconds


class CacheService:
    def __init__(self, max_entries: int = 4096, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds

    def _key(
        self,
        user_model_id: str,
        prompt: str,
        temperature: float | None,
        tools: list[Any] | None,
        key_hash: str = "",
    ) -> str:
        salt = settings.PANEL_API_KEY.encode()
        prompt_hmac = hmac.new(salt, prompt.encode(), hashlib.sha256).hexdigest()[:32]
        tools_json = json.dumps(tools, sort_keys=True) if tools else ""
        tools_hash = hashlib.sha256(tools_json.encode()).hexdigest()[:16]
        temp_str = f"{temperature:.4f}" if temperature is not None else "none"
        tenant = (key_hash or "panel")[:8]
        raw = f"{tenant}:{user_model_id}:{prompt_hmac}:{temp_str}:{tools_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(
        self,
        user_model_id: str,
        prompt: str,
        temperature: float | None,
        tools: list[Any] | None,
        key_hash: str = "",
    ) -> str | None:
        key = self._key(user_model_id, prompt, temperature, tools, key_hash)
        return await self._get(key)

    async def set(
        self,
        user_model_id: str,
        prompt: str,
        temperature: float | None,
        tools: list[Any] | None,
        value: str,
        key_hash: str = "",
    ) -> None:
        key = self._key(user_model_id, prompt, temperature, tools, key_hash)
        await self._set(key, value)

    async def get_stream(
        self,
        user_model_id: str,
        prompt: str,
        temperature: float | None,
        tools: list[Any] | None,
        key_hash: str = "",
    ) -> str | None:
        key = f"stream:{self._key(user_model_id, prompt, temperature, tools, key_hash)}"
        return await self._get(key)

    async def set_stream(
        self,
        user_model_id: str,
        prompt: str,
        temperature: float | None,
        tools: list[Any] | None,
        value: str,
        key_hash: str = "",
    ) -> None:
        key = f"stream:{self._key(user_model_id, prompt, temperature, tools, key_hash)}"
        await self._set(key, value)

    async def _get(self, key: str) -> str | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.monotonic():
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return entry.value

    async def _set(self, key: str, value: str) -> None:
        async with self._lock:
            if key in self._store:
                self._store[key] = CacheEntry(value, self._ttl_seconds)
                self._store.move_to_end(key)
            else:
                if len(self._store) >= self._max_entries:
                    evicted_key, _ = self._store.popitem(last=False)
                    logger.debug("cache.evicted", key_prefix=evicted_key[:8])
                self._store[key] = CacheEntry(value, self._ttl_seconds)

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


__all__ = ["CacheService", "get_cache", "CACHE_TTL_SECONDS"]
