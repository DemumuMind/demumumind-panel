"""FinOps — per-key budgets and usage accounting.

Budget comes from ApiKey.monthly_budget (SSOT in DB). Spend is tracked
in agent_usage rows, attributed to the key via agent_type="key_<first8>"
or the caller's X-Agent-Type. check_budget raises BudgetError when spent
>= budget (budget>0 only).
"""

from __future__ import annotations

import datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BudgetError
from app.models import AgentUsage, ApiKey
from app.schemas import AgentUsageOut, PaginatedResponse, UsagePoint

logger = structlog.get_logger(__name__)


def key_agent_type(key_hash: str) -> str:
    return f"key_{key_hash[:8]}"


class FinopsService:
    def __init__(self) -> None:
        self._budgets: dict[str, float] = {}

    async def load_budgets(self, session: AsyncSession) -> dict[str, float]:
        rows = await session.execute(select(ApiKey.key_hash, ApiKey.monthly_budget))
        self._budgets = {kh: budget for kh, budget in rows.all()}
        return self._budgets

    async def check_budget(self, session: AsyncSession, key_hash: str) -> None:
        budget = self._budgets.get(key_hash, 0.0)
        if budget <= 0:
            return
        spent_row = await session.execute(
            select(func.coalesce(func.sum(AgentUsage.cost_usd), 0.0)).where(
                AgentUsage.agent_type == key_agent_type(key_hash)
            )
        )
        spent = float(spent_row.scalar_one())
        if spent >= budget:
            logger.info("finops.budget_exceeded", key_prefix=key_hash[:8], spent=spent, budget=budget)
            raise BudgetError(message=f"Monthly budget exceeded: ${budget:.2f}")

    async def record_usage(
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

    async def usage_stats(self, session: AsyncSession, limit: int, offset: int) -> PaginatedResponse[AgentUsageOut]:
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

    async def usage_timeseries(self, session: AsyncSession, days: int = 30) -> list[UsagePoint]:
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
        cutoff_naive = cutoff.replace(tzinfo=None)
        base = select(
            func.date(AgentUsage.created_at).label("d"),
            func.sum(AgentUsage.tokens_in).label("tokens_in"),
            func.sum(AgentUsage.tokens_out).label("tokens_out"),
            func.sum(AgentUsage.cost_usd).label("cost_usd"),
            func.count(AgentUsage.id).label("requests"),
        ).where(AgentUsage.created_at >= cutoff_naive).group_by("d").order_by("d")
        rows = await session.execute(base)
        return [
            UsagePoint(
                date=str(r.d),
                tokens_in=int(r.tokens_in or 0),
                tokens_out=int(r.tokens_out or 0),
                cost_usd=float(r.cost_usd or 0.0),
                requests=int(r.requests or 0),
            )
            for r in rows.all()
        ]

    async def usage_by_provider(
        self, session: AsyncSession, limit: int, offset: int
    ) -> PaginatedResponse[AgentUsageOut]:
        from app.models import Provider as ProviderModel

        base = (
            select(
                func.coalesce(ProviderModel.name, "unknown").label("provider_name"),
                func.sum(AgentUsage.tokens_in).label("tokens_in"),
                func.sum(AgentUsage.tokens_out).label("tokens_out"),
                func.sum(AgentUsage.cost_usd).label("cost_usd"),
                func.count(AgentUsage.id).label("requests"),
            )
            .outerjoin(ProviderModel, ProviderModel.id == AgentUsage.provider_id)
            .group_by(AgentUsage.provider_id)
        )
        total = await session.execute(select(func.count()).select_from(base.subquery()))
        total_count = int(total.scalar_one() or 0)
        rows = await session.execute(base.order_by(func.count(AgentUsage.id).desc()).limit(limit).offset(offset))
        items = [
            AgentUsageOut(
                agent_type=r.provider_name,
                tokens_in=int(r.tokens_in or 0),
                tokens_out=int(r.tokens_out or 0),
                cost_usd=float(r.cost_usd or 0.0),
                requests=int(r.requests or 0),
            )
            for r in rows.all()
        ]
        return PaginatedResponse[AgentUsageOut](items=items, total=total_count, limit=limit, offset=offset)


_finops: FinopsService | None = None


def get_finops() -> FinopsService:
    global _finops
    if _finops is None:
        _finops = FinopsService()
    return _finops


__all__ = ["FinopsService", "get_finops", "key_agent_type"]
