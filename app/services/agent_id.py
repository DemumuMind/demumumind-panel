"""Dynamic agent registry — agent_types table + usage logging + stats."""

from __future__ import annotations

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentType, AgentUsage
from app.schemas import AgentUsageOut, PaginatedResponse

logger = structlog.get_logger(__name__)


class AgentRegistry:
    async def register(self, session: AsyncSession, agent_type: str) -> None:
        exists = await session.execute(select(AgentType.id).where(AgentType.name == agent_type).limit(1))
        if exists.scalar_one_or_none() is None:
            session.add(AgentType(name=agent_type))
            await session.commit()

    async def log_usage(
        self,
        session: AsyncSession,
        *,
        agent_type: str,
        provider_id: str | None,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        row = AgentUsage(
            agent_type=agent_type,
            provider_id=provider_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
        session.add(row)
        await session.commit()

    async def stats(self, session: AsyncSession, limit: int, offset: int) -> PaginatedResponse[AgentUsageOut]:
        base = select(
            AgentUsage.agent_type,
            func.sum(AgentUsage.tokens_in).label("tokens_in"),
            func.sum(AgentUsage.tokens_out).label("tokens_out"),
            func.sum(AgentUsage.cost_usd).label("cost_usd"),
            func.count(AgentUsage.id).label("requests"),
        ).group_by(AgentUsage.agent_type)
        total = await session.execute(select(func.count()).select_from(base.subquery()))
        total_count = int(total.scalar_one() or 0)
        rows = await session.execute(base.order_by(AgentUsage.agent_type).limit(limit).offset(offset))
        items = [
            AgentUsageOut(
                agent_type=r.agent_type,
                tokens_in=int(r.tokens_in or 0),
                tokens_out=int(r.tokens_out or 0),
                cost_usd=float(r.cost_usd or 0.0),
                requests=int(r.requests or 0),
            )
            for r in rows.all()
        ]
        return PaginatedResponse[AgentUsageOut](items=items, total=total_count, limit=limit, offset=offset)


_registry: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


__all__ = ["AgentRegistry", "get_registry"]
