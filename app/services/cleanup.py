"""Periodic cleanup / GC — soft deactivation + safe physical deletes.

Principles:
- Providers/models are NEVER physically deleted by automation (they may be
  config worth keeping); they are softly deactivated (is_active=0).
- Physical DELETE only for groups with no references (no children, no keys)
  and for old telemetry (AgentUsage retention).
- Missing-from-listing alone never deactivates a model (hybrid providers
  don't list everything); a model is deactivated only after it repeatedly
  fails the real test AND is missing from the listing.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import structlog
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentUsage, ApiKey, Group, Model, Provider
from app.schemas import CleanupReport
from app.services.discovery import discover_provider_models, test_provider_model
from app.services.finops import key_agent_type
from app.services.provider_manager import get_manager

logger = structlog.get_logger(__name__)

MODEL_FAIL_THRESHOLD = 3
APIKEY_INACTIVE_DAYS = 30
USAGE_RETENTION_DAYS = 90


def _now() -> datetime.datetime:
    # SQLite stores datetimes without tzinfo, so compare in naive UTC.
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


async def run_cleanup(session: AsyncSession, max_age_days: int | None = None) -> CleanupReport:
    report = CleanupReport(
        providers_deactivated=0,
        models_deactivated=0,
        groups_deleted=0,
        keys_deactivated=0,
        usage_deleted=0,
        warnings=[],
    )

    # 1. Providers: deactivate if /models is unreachable.
    providers = (await session.execute(select(Provider))).scalars().all()
    for provider in providers:
        if not provider.is_active:
            continue
        try:
            await discover_provider_models(provider, "cleanup")
        except Exception as exc:
            provider.is_active = 0
            report.providers_deactivated += 1
            report.warnings.append(f"provider {provider.name}: unreachable ({type(exc).__name__})")
            logger.info("cleanup.provider_deactivated", provider=provider.name, reason=type(exc).__name__)

    # 2. Models: count failures; deactivate only if repeatedly failing AND missing from listing.
    #    Premium models (403 deposit/access_denied) are NEVER deactivated.
    models = (await session.execute(select(Model).where(Model.is_active == 1))).scalars().all()
    providers_map = {p.id: p for p in providers}
    for model in models:
        provider_rec = providers_map.get(model.provider_id)
        if provider_rec is None:
            continue
        meta = _load_meta(model.meta)
        if meta.get("premium"):
            continue  # premium models are not system errors
        status = await test_provider_model(provider_rec, model.internal_model, "cleanup")
        if status.ok or status.category == "premium":
            meta["test_fail_count"] = 0
            if status.category == "premium":
                meta["premium"] = True
            model.meta = json.dumps(meta)
            continue
        meta["test_fail_count"] = int(meta.get("test_fail_count", 0)) + 1
        fail_count = int(meta["test_fail_count"])
        model.meta = json.dumps(meta)
        if fail_count >= MODEL_FAIL_THRESHOLD and meta.get("missing_from_listing"):
            model.is_active = 0
            report.models_deactivated += 1
            logger.info(
                "cleanup.model_deactivated",
                model=model.user_model_id,
                fail_count=fail_count,
            )

    # 2b. Mark missing_from_listing on models not in the provider listing (no deactivation by itself).
    for provider in providers:
        try:
            listed = set(await discover_provider_models(provider, "cleanup"))
        except Exception:
            continue
        provider_models = [
            m for m in models if m.provider_id == provider.id and m.is_active
        ]
        for model in provider_models:
            if model.internal_model not in listed:
                meta = _load_meta(model.meta)
                if not meta.get("missing_from_listing"):
                    meta["missing_from_listing"] = True
                    model.meta = json.dumps(meta)
                    logger.info(
                        "cleanup.model_missing_from_listing",
                        model=model.user_model_id,
                        provider=provider.name,
                    )

    # 3. Groups: delete groups with no children and no keys.
    group_rows = (await session.execute(select(Group))).scalars().all()
    for group in group_rows:
        has_children = any(g.parent_group_id == group.id for g in group_rows)
        key_count = int(
            (await session.execute(
                select(func.count()).select_from(ApiKey).where(ApiKey.group_id == group.id)
            )).scalar_one()
            or 0
        )
        if not has_children and key_count == 0:
            await session.delete(group)
            report.groups_deleted += 1
            logger.info("cleanup.group_deleted", group=group.name)

    # 4. ApiKeys: deactivate if no usage and older than threshold.
    cutoff_key = _now() - datetime.timedelta(days=APIKEY_INACTIVE_DAYS)
    keys = (await session.execute(select(ApiKey).where(ApiKey.is_active == 1))).scalars().all()
    for key in keys:
        if key.created_at > cutoff_key:
            continue
        usage_count = int(
            (await session.execute(
                select(func.count())
                .select_from(AgentUsage)
                .where(AgentUsage.agent_type == key_agent_type(key.key_hash))
            )).scalar_one()
            or 0
        )
        if usage_count == 0:
            key.is_active = 0
            report.keys_deactivated += 1
            logger.info("cleanup.key_deactivated", key_prefix=key.key_hash[:8])

    # 5. AgentUsage retention.
    retention_days = max_age_days if max_age_days is not None else USAGE_RETENTION_DAYS
    cutoff_usage = _now() - datetime.timedelta(days=retention_days)
    old_rows = await session.execute(
        select(AgentUsage.id).where(AgentUsage.created_at < cutoff_usage)
    )
    old_ids = [row[0] for row in old_rows.all()]
    if old_ids:
        await session.execute(sa_delete(AgentUsage).where(AgentUsage.id.in_(old_ids)))
        report.usage_deleted = len(old_ids)
        logger.info("cleanup.usage_retention", deleted=len(old_ids), retention_days=retention_days)

    await session.commit()
    await get_manager().refresh()
    logger.info("cleanup.done", **report.model_dump(exclude={"warnings"}))
    return report


def _load_meta(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


__all__ = ["run_cleanup", "CleanupReport"]
