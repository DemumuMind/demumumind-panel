"""Pydantic v2 DTOs — request/response contracts.

`metadata` fields in provider/model payloads map to the DB column
`metadata` (stored as TEXT JSON; the ORM attribute is `meta`).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")

ProtocolName = Literal[
    "openai", "anthropic", "gemini", "google", "vertex",
    "cohere", "ollama", "azure",
]


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str | None = None
    status_code: int | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class HealthOut(BaseModel):
    status: str
    version: str
    checks: dict[str, str]


# --- Providers ---


class CreateProviderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = None
    protocol: ProtocolName = "openai"
    is_default: bool = False
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        if "://" not in v:
            raise ValueError("base_url must include scheme (http:// or https://)")
        return v.rstrip("/")


class UpdateProviderRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    protocol: ProtocolName | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("base_url")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        if v is not None and "://" not in v:
            raise ValueError("base_url must include scheme (http:// or https://)")
        return v.rstrip("/") if v else v


def _parse_json_field(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_url: str
    protocol: str
    is_default: bool
    is_active: bool
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="meta")
    created_at: datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def _parse_meta(cls, v: Any) -> dict[str, Any]:
        return _parse_json_field(v)


class TestProviderResult(BaseModel):
    ok: bool
    models: list[str]
    message: str | None = None


# --- Discovery / model workability ---


class DiscoveredModelStatus(BaseModel):
    internal_model: str
    ok: bool
    category: Literal["ok", "premium", "rate_limited", "listed", "error"] = "error"
    latency_ms: int | None = None
    error: str | None = None


class ModelDiscoveryResult(BaseModel):
    provider_id: str
    provider_name: str
    total: int
    imported: int
    skipped: int
    ok_count: int
    models: list[DiscoveredModelStatus]


# --- Provider key pool ---


class CreateProviderKeyRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=2000)


class ProviderKeyOut(BaseModel):
    id: str
    provider_id: str
    api_key_masked: str
    is_active: bool
    last_used_at: datetime | None
    success_count: int
    fail_count: int
    created_at: datetime


# --- Cleanup report ---


class CleanupReport(BaseModel):
    providers_deactivated: int
    models_deactivated: int
    groups_deleted: int
    keys_deactivated: int
    usage_deleted: int
    warnings: list[str]


# --- Models ---


class CreateModelRequest(BaseModel):
    provider_id: str
    user_model_id: str = Field(min_length=1, max_length=200)
    internal_model: str = Field(min_length=1, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class UpdateModelRequest(BaseModel):
    provider_id: str | None = None
    internal_model: str | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_id: str
    user_model_id: str
    internal_model: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="meta")
    is_active: bool
    created_at: datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def _parse_meta(cls, v: Any) -> dict[str, Any]:
        return _parse_json_field(v)


# --- Groups / Keys ---


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_group_id: str | None = None
    limit_enforcement: Literal["independent", "shared"] = "independent"
    model_slugs: dict[str, Any] = Field(default_factory=dict)


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    parent_group_id: str | None
    limit_enforcement: str
    model_slugs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("model_slugs", mode="before")
    @classmethod
    def _parse_slugs(cls, v: Any) -> dict[str, Any]:
        return _parse_json_field(v)


class CreateApiKeyRequest(BaseModel):
    group_id: str | None = None
    model_mapping: dict[str, str] = Field(default_factory=dict)
    monthly_budget: float = Field(default=0.0, ge=0.0)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    group_id: str | None
    model_mapping: dict[str, str]
    monthly_budget: float
    key_hash: str
    created_at: datetime

    @field_validator("model_mapping", mode="before")
    @classmethod
    def _parse_mapping(cls, v: Any) -> dict[str, str]:
        parsed = _parse_json_field(v)
        return {str(k): str(val) for k, val in parsed.items()}


class ApiKeyCreated(BaseModel):
    id: str
    api_key: str  # raw key, returned exactly once


# --- Chat payloads (OpenAI-compatible) ---


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool", "function"]
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    response_format: dict[str, Any] | None = None
    user: str | None = None


class AnthropicMessageRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    system: str | list[Any] | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None


class GeminiGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = ""
    contents: list[dict[str, Any]] = Field(default_factory=list)
    systemInstruction: dict[str, Any] | None = None
    generationConfig: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    stream: bool = False


class ImageGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    prompt: str = Field(min_length=1)
    n: int | None = None
    size: str | None = None
    quality: str | None = None
    response_format: str | None = None
    style: str | None = None


# --- Admin / auth / misc ---


class LoginRequest(BaseModel):
    panel_api_key: str


class AgentUsageOut(BaseModel):
    agent_type: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    requests: int
    free_requests: int = 0
    unlimited_requests: int = 0
    unknown_requests: int = 0
    cached_requests: int = 0


class UsageRowOut(BaseModel):
    agent_type: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    requests: int
    free_requests: int = 0
    unlimited_requests: int = 0
    unknown_requests: int = 0
    cached_requests: int = 0


class UsagePoint(BaseModel):
    date: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    requests: int
    free_requests: int = 0
    unlimited_requests: int = 0
    unknown_requests: int = 0
    cached_requests: int = 0


class ModelPricingUpdate(BaseModel):
    """Manual pricing/free override for a model (source='manual')."""

    price_prompt_per_token: float | None = None
    price_completion_per_token: float | None = None
    price_request: float | None = None
    free: bool | None = None
    limit_requests_per_minute: int | None = None
    limit_requests_per_day: int | None = None


class PluginOut(BaseModel):
    name: str
    signature_valid: bool
    size_bytes: int
    loaded: bool
    error: str | None = None


class PluginInvokeRequest(BaseModel):
    fn: str = Field(min_length=1)
    args: Any = None


class PluginInvokeResult(BaseModel):
    ok: bool
    result: Any = None
    error: str | None = None


# --- MCP ---


class CreateMcpServerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=500)
    description: str = ""


class CreateMcpPermissionRequest(BaseModel):
    agent_type: str = Field(min_length=1, max_length=100)
    tool_name: str = Field(min_length=1, max_length=200)
    allowed: bool = True
    budget_per_day: float = 0.0


class McpServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_url: str
    description: str
    created_at: datetime


class McpPermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_type: str
    tool_name: str
    allowed: bool
    budget_per_day: float
    created_at: datetime


class ProviderTestRunOut(BaseModel):
    id: str
    provider_id: str
    provider_name: str
    kind: str
    ok_count: int
    total: int
    created_at: datetime
    result: dict[str, Any] | None = None


__all__ = [
    "ErrorResponse",
    "PaginatedResponse",
    "HealthOut",
    "CreateProviderRequest",
    "UpdateProviderRequest",
    "ProviderOut",
    "TestProviderResult",
    "DiscoveredModelStatus",
    "ModelDiscoveryResult",
    "CreateProviderKeyRequest",
    "ProviderKeyOut",
    "CleanupReport",
    "CreateModelRequest",
    "UpdateModelRequest",
    "ModelOut",
    "CreateGroupRequest",
    "GroupOut",
    "CreateApiKeyRequest",
    "ApiKeyOut",
    "ApiKeyCreated",
    "ChatMessage",
    "ChatCompletionRequest",
    "AnthropicMessageRequest",
    "GeminiGenerateRequest",
    "ImageGenerationRequest",
    "LoginRequest",
    "AgentUsageOut",
    "UsageRowOut",
    "UsagePoint",
    "ModelPricingUpdate",
    "PluginOut",
    "PluginInvokeRequest",
    "PluginInvokeResult",
    "CreateMcpServerRequest",
    "CreateMcpPermissionRequest",
    "McpServerOut",
    "McpPermissionOut",
    "ProviderTestRunOut",
]
