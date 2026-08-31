"""HTTP middleware — key hashing, auth state, X-Request-ID, CORS, agent type.

Keys are hashed with hmac_sha256(raw, salt=PANEL_API_KEY) — never stored raw.
Client key validation looks up the computed key_hash in the DB.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

import structlog
from fastapi import Request
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import settings
from app.core.db import AsyncSessionLocal
from app.models import ApiKey

logger = structlog.get_logger(__name__)


def hash_key(raw_key: str) -> str:
    return hmac.new(settings.PANEL_API_KEY.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


class AuthState:
    def __init__(self, request: Request) -> None:
        self._request = request

    async def is_panel_authorized(self) -> bool:
        token = _bearer_token(self._request.headers.get("authorization"))
        if not token:
            return False
        return hmac.compare_digest(token, settings.PANEL_API_KEY)

    async def client_key_hash(self) -> str | None:
        raw = self._request.headers.get("x-api-key") or _bearer_token(
            self._request.headers.get("authorization")
        )
        if not raw:
            raw = self._request.headers.get("x-goog-api-key")
        if not raw:
            raw = self._request.query_params.get("key")
        if not raw:
            return None
        key_hash = hash_key(raw)
        async with AsyncSessionLocal() as session:
            row = await session.execute(select(ApiKey.key_hash).where(ApiKey.key_hash == key_hash).limit(1))
            if row.scalar_one_or_none() is None:
                return None
        return key_hash


class XRequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def get_agent_type(request: Request) -> str:
    agent = request.headers.get("X-Agent-Type", "default").strip()
    return agent or "default"


__all__ = [
    "hash_key",
    "AuthState",
    "XRequestIDMiddleware",
    "get_agent_type",
]
