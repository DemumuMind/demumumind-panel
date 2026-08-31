"""Hot reload — watch for provider/model/key changes without restart.

Primary: Redis keyspace pub/sub (`__keyevent@0__:set/:del/:expired/:hset`)
on `model_table:*` / `api_key:*` / `provider:*` keys -> provider_manager.refresh().
Fallback: 5s polling of row counts when Redis is unavailable. Never crashes.
"""

from __future__ import annotations

import asyncio

import structlog
from redis.asyncio import Redis
from sqlalchemy import func, select

from app.core.db import AsyncSessionLocal
from app.core.redis import get_redis
from app.models import Model, Provider
from app.services.provider_manager import get_manager

logger = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 5.0
_WATCH_PATTERNS = ("model_table:", "api_key:", "provider:")

_keyspace_patterns = [
    "__keyevent@0__:set",
    "__keyevent@0__:del",
    "__keyevent@0__:expired",
    "__keyevent@0__:hset",
]


class HotReload:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []
        self._last_counts: tuple[int, int] | None = None

    async def start(self) -> None:
        redis = await get_redis()
        if redis is not None:
            await self._enable_keyspace_events(redis)
            self._tasks.append(asyncio.create_task(self._redis_loop(redis)))
            logger.info("hot_reload.started_redis")
        self._tasks.append(asyncio.create_task(self._polling_loop()))
        logger.info("hot_reload.started_polling")

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks = []

    async def _enable_keyspace_events(self, redis: Redis) -> None:
        try:
            await redis.config_set("notify-keyspace-events", "KEA")
        except Exception:
            logger.warning("hot_reload.keyspace_events_denied_fallback_polling")

    async def _redis_loop(self, redis: Redis) -> None:
        try:
            pubsub = redis.pubsub()
            await pubsub.psubscribe(*_keyspace_patterns)
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                channel = message.get("channel", "")
                data = message.get("data", "")
                if isinstance(channel, bytes):
                    channel = channel.decode()
                if isinstance(data, bytes):
                    data = data.decode()
                if any(pat in str(channel) for pat in _WATCH_PATTERNS) or any(
                    pat in str(data) for pat in _WATCH_PATTERNS
                ):
                    await get_manager().refresh()
                    logger.info("hot_reload.refresh_via_redis", channel=channel, key=data)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("hot_reload.redis_loop_error")

    async def _polling_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                counts = await self._count_rows()
                if self._last_counts is not None and counts != self._last_counts:
                    await get_manager().refresh()
                    logger.info("hot_reload.refresh_via_polling", prev=self._last_counts, now=counts)
                self._last_counts = counts
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("hot_reload.polling_error")

    async def _count_rows(self) -> tuple[int, int]:
        async with AsyncSessionLocal() as session:
            p = await session.execute(select(func.count()).select_from(Provider))
            m = await session.execute(select(func.count()).select_from(Model))
            return int(p.scalar_one()), int(m.scalar_one())


_hot_reload: HotReload | None = None


def get_hot_reload() -> HotReload:
    global _hot_reload
    if _hot_reload is None:
        _hot_reload = HotReload()
    return _hot_reload


__all__ = ["HotReload", "get_hot_reload"]
