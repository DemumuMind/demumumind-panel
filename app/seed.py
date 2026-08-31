"""Idempotent seed — default group + example placeholder provider.

Runs at startup (lifespan) and via POST /v1/admin/seed. INSERT OR IGNORE
semantics: never duplicates, never overwrites user data.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Group, Provider

logger = structlog.get_logger(__name__)

DEFAULT_GROUP = "default"
EXAMPLE_PROVIDER_NAME = "Example OpenAI-compatible"


async def run_seed(session: AsyncSession) -> dict[str, int]:
    created = {"groups": 0, "providers": 0}

    existing_group = await session.execute(select(Group).where(Group.name == DEFAULT_GROUP).limit(1))
    if existing_group.scalar_one_or_none() is None:
        session.add(Group(name=DEFAULT_GROUP, limit_enforcement="independent", model_slugs="{}"))
        created["groups"] = 1

    existing_provider = await session.execute(
        select(Provider).where(Provider.name == EXAMPLE_PROVIDER_NAME).limit(1)
    )
    if existing_provider.scalar_one_or_none() is None:
        session.add(
            Provider(
                name=EXAMPLE_PROVIDER_NAME,
                base_url="https://api.openai.com/v1",
                api_key=None,
                protocol="openai",
                is_default=0,
                is_active=1,
                meta="{}",
            )
        )
        created["providers"] = 1

    await session.commit()
    logger.info("seed.done", created=created)
    return created


__all__ = ["run_seed", "DEFAULT_GROUP"]
