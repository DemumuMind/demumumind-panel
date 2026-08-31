"""Redis client access. Optional — returns None when unavailable so all
callers can fall back (e.g. hot_reload polling, rate-limit disabled)."""

from __future__ import annotations

import structlog
from redis.asyncio import Redis

from app.config import settings

logger = structlog.get_logger(__name__)

_redis: Redis | None = None
_checked = False


async def get_redis() -> Redis | None:
    global _redis, _checked
    if _checked:
        return _redis
    if not settings.REDIS_URL:
        logger.info("redis.disabled_no_url")
        _checked = True
        return None
    try:
        client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        _redis = client
        logger.info("redis.connected")
    except Exception:
        logger.warning("redis.unavailable_fallback_disabled")
        _redis = None
    _checked = True
    return _redis


async def close_redis() -> None:
    global _redis, _checked
    if _redis is not None:
        await _redis.aclose()
    _redis = None
    _checked = False


__all__ = ["get_redis", "close_redis"]
