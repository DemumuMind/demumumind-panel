"""MCP JSON-RPC 2.0 service — initialize, tools/list, tools/call.

Upstream MCP servers are called over HTTP POST (JSON-RPC 2.0) via the
shared ProviderPool client. tools/call is gated by mcp_permissions
(allowed + budget_per_day). Errors return JSON-RPC error objects, never raise.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import McpPermission, McpServer
from app.services.pool import get_pool

logger = structlog.get_logger(__name__)

JsonDict = dict[str, Any]


class McpService:
    async def handle(self, session: AsyncSession, body: JsonDict) -> JsonDict:
        method = body.get("method", "")
        params = body.get("params") or {}
        rid = body.get("id")
        try:
            if method == "initialize":
                result = await self.initialize(session, params)
            elif method == "tools/list":
                result = await self.tools_list(session, params.get("server", ""))
            elif method == "tools/call":
                result = await self.tools_call(
                    session,
                    server_name=params.get("server", ""),
                    tool_name=params.get("tool", ""),
                    arguments=params.get("arguments") or {},
                    agent_type=params.get("agent_type", "default"),
                )
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except Exception as exc:  # JSON-RPC errors are data, not exceptions
            logger.warning("mcp.error", method=method, error=str(exc))
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(exc)}}

    async def initialize(self, session: AsyncSession, params: JsonDict) -> JsonDict:
        protocol_version = params.get("protocolVersion", "2024-11-05")
        capabilities = params.get("capabilities") or {}
        return {
            "protocolVersion": protocol_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "demumumind-mcp", "version": "0.1.0"},
            "clientCapabilities": capabilities,
        }

    async def _server(self, session: AsyncSession, server_name: str) -> McpServer:
        row = await session.execute(select(McpServer).where(McpServer.name == server_name).limit(1))
        server = row.scalar_one_or_none()
        if server is None:
            raise ValueError(f"Unknown MCP server: {server_name}")
        return server

    async def _call_upstream(self, server: McpServer, body: JsonDict, request_id: str) -> JsonDict:
        pool = get_pool()
        resp = await pool.request_url(
            url=server.base_url,
            headers={"Content-Type": "application/json"},
            method="POST",
            json_body=body,
            request_id=request_id,
        )
        if resp.status_code >= 400:
            raise ValueError(f"upstream MCP error {resp.status_code}: {resp.text[:200]}")
        return cast(JsonDict, resp.json())

    async def tools_list(self, session: AsyncSession, server_name: str) -> JsonDict:
        server = await self._server(session, server_name)
        body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/list", "params": {}}
        result = await self._call_upstream(server, body, str(uuid.uuid4()))
        return cast(JsonDict, result.get("result", result))

    async def tools_call(
        self,
        session: AsyncSession,
        server_name: str,
        tool_name: str,
        arguments: JsonDict,
        agent_type: str,
    ) -> JsonDict:
        perm_row = await session.execute(
            select(McpPermission).where(
                McpPermission.agent_type == agent_type,
                McpPermission.tool_name == tool_name,
            ).limit(1)
        )
        perm = perm_row.scalar_one_or_none()
        if perm is None or not perm.allowed:
            raise ValueError(f"Tool not permitted for agent_type {agent_type}: {tool_name}")
        server = await self._server(session, server_name)
        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        result = await self._call_upstream(server, body, str(uuid.uuid4()))
        return cast(JsonDict, result.get("result", result))


_mcp: McpService | None = None


def get_mcp() -> McpService:
    global _mcp
    if _mcp is None:
        _mcp = McpService()
    return _mcp


__all__ = ["McpService", "get_mcp"]
