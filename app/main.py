"""DemumuMind Panel — FastAPI application entrypoint.

Lifespan: init_db -> provider_manager.load -> seed -> hot_reload.start.
CORS from config (never *), X-Request-ID middleware, slowapi rate limiter,
structured error handlers. BIND_ADDR from config.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.v1.admin_routes import admin_router, auth_router
from app.api.v1.mcp import mcp_router
from app.api.v1.middleware import XRequestIDMiddleware
from app.api.v1.routes import limiter, root_router, v1_router
from app.config import settings
from app.core.db import AsyncSessionLocal, init_db
from app.core.errors import register_error_handlers
from app.core.redis import close_redis
from app.schemas import ErrorResponse
from app.seed import run_seed
from app.services.hot_reload import get_hot_reload
from app.services.pool import get_pool
from app.services.provider_manager import get_manager

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("app.startup.begin")
    await init_db()
    async with AsyncSessionLocal() as session:
        await get_manager().load(session)
        await run_seed(session)
    await get_manager().refresh()
    await get_hot_reload().start()
    logger.info("app.startup.done")
    yield
    await get_hot_reload().stop()
    await get_pool().aclose()
    await close_redis()
    logger.info("app.shutdown.done")


app = FastAPI(
    title="DemumuMind Panel",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter


def _rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=429,
        content=ErrorResponse(
            error="rate_limited",
            detail="Rate limit exceeded: 100/minute",
            request_id=rid,
            status_code=429,
        ).model_dump(),
        headers={"X-Request-ID": rid} if rid else None,
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(XRequestIDMiddleware)

register_error_handlers(app)

app.include_router(root_router)
app.include_router(v1_router)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(mcp_router)


__all__ = ["app"]
