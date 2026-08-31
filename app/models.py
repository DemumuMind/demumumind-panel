"""SQLAlchemy 2.0 async models — 8 tables, SSOT for the schema.

Booleans are stored as INTEGER 0/1, JSON blobs as TEXT (per spec).
All `metadata` columns are mapped to Python attribute `meta` because
`metadata` is reserved by SQLAlchemy's Declarative API; the DB column
name stays `metadata` to match the canonical DDL.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class Base(DeclarativeBase):
    pass


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    protocol: Mapped[str] = mapped_column(String, default="openai")
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    meta: Mapped[str] = mapped_column("metadata", Text, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Model(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    provider_id: Mapped[str] = mapped_column(
        String, ForeignKey("providers.id", ondelete="CASCADE"), index=True
    )
    user_model_id: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, index=True
    )
    internal_model: Mapped[str] = mapped_column(String, nullable=False)
    meta: Mapped[str] = mapped_column("metadata", Text, default="{}")
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)
    parent_group_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    limit_enforcement: Mapped[str] = mapped_column(String, default="independent")
    model_slugs: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    key_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    group_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    model_mapping: Mapped[str] = mapped_column(Text, default="{}")
    monthly_budget: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class AgentType(Base):
    __tablename__ = "agent_types"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class McpServer(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class McpPermission(Base):
    __tablename__ = "mcp_permissions"
    __table_args__ = (UniqueConstraint("agent_type", "tool_name"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_type: Mapped[str] = mapped_column(String, nullable=False)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    allowed: Mapped[int] = mapped_column(Integer, default=1)
    budget_per_day: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class AgentUsage(Base):
    __tablename__ = "agent_usage"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("providers.id", ondelete="SET NULL"), nullable=True
    )
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class ProviderKey(Base):
    __tablename__ = "provider_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    provider_id: Mapped[str] = mapped_column(
        String, ForeignKey("providers.id", ondelete="CASCADE"), index=True
    )
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


__all__ = [
    "Base",
    "Provider",
    "Model",
    "Group",
    "ApiKey",
    "AgentType",
    "McpServer",
    "McpPermission",
    "AgentUsage",
    "ProviderKey",
]
