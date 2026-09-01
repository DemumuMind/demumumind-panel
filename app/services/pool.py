"""httpx AsyncClient pool — single long-lived client with keepalive.

Per-protocol auth headers, X-Request-ID forwarding, 30s timeout,
32 max keepalive connections.
"""

from __future__ import annotations

from typing import Any

import structlog
from httpx import AsyncClient, Limits, Response, Timeout

from app.models import Provider

logger = structlog.get_logger(__name__)

_PROTOCOL_HEADERS = {
    "openai": ("Authorization", "Bearer {key}"),
    "azure": ("api-key", "{key}"),
    "anthropic": ("x-api-key", "{key}"),
    "gemini": ("x-goog-api-key", "{key}"),
    "cohere": ("Authorization", "Bearer {key}"),
    "ollama": ("Authorization", "Bearer {key}"),
}


class ProviderPool:
    def __init__(self) -> None:
        self._client: AsyncClient | None = None

    def _get_client(self) -> AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = AsyncClient(
                limits=Limits(max_keepalive_connections=32, max_connections=64),
                timeout=Timeout(30.0),
            )
        return self._client

    def auth_headers(self, provider: Provider) -> dict[str, str]:
        headers: dict[str, str] = {}
        protocol = provider.protocol or "openai"
        if provider.api_key:
            name, templ = _PROTOCOL_HEADERS.get(protocol, _PROTOCOL_HEADERS["openai"])
            headers[name] = templ.format(key=provider.api_key)
        if protocol == "anthropic":
            headers.setdefault("anthropic-version", "2023-06-01")
        return headers

    def _url(self, provider: Provider, path: str) -> str:
        base = provider.base_url.rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    async def request(
        self,
        *,
        provider: Provider,
        path: str,
        method: str,
        json_body: dict[str, Any] | None,
        request_id: str,
        request_timeout: float | None = None,
    ) -> Response:
        client = self._get_client()
        headers = self.auth_headers(provider)
        headers["X-Request-ID"] = request_id
        kwargs: dict[str, Any] = {}
        if request_timeout is not None:
            kwargs["timeout"] = Timeout(request_timeout)
        return await client.request(
            method.upper(), self._url(provider, path), headers=headers, json=json_body, **kwargs
        )

    async def request_stream(
        self,
        *,
        provider: Provider,
        path: str,
        method: str,
        json_body: dict[str, Any] | None,
        request_id: str,
    ) -> Response:
        client = self._get_client()
        headers = self.auth_headers(provider)
        headers["X-Request-ID"] = request_id
        request = client.build_request(method.upper(), self._url(provider, path), headers=headers, json=json_body)
        return await client.send(request, stream=True)

    async def request_url(
        self,
        *,
        url: str,
        headers: dict[str, str],
        method: str,
        json_body: dict[str, Any] | None,
        request_id: str,
    ) -> Response:
        client = self._get_client()
        all_headers = dict(headers)
        all_headers["X-Request-ID"] = request_id
        return await client.request(method.upper(), url, headers=all_headers, json=json_body)

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None


_pool: ProviderPool | None = None


def get_pool() -> ProviderPool:
    global _pool
    if _pool is None:
        _pool = ProviderPool()
    return _pool


__all__ = ["ProviderPool", "get_pool"]
