"""MCP JSON-RPC 2.0 HTTP endpoint — POST /mcp."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.mcp import get_mcp

mcp_router = APIRouter(tags=["mcp"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


@mcp_router.post("/mcp")
async def mcp_endpoint(body: dict[str, Any], request: Request, session: SessionDep) -> dict[str, Any]:
    return await get_mcp().handle(session, body)


__all__ = ["mcp_router"]
