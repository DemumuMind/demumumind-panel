"""Input/output guardrails — regex rules and JSON-schema validation.

Fail-open on invalid regex patterns (log warning, skip rule).
Fail-closed on guardrails: validate_input/output raise AppError(422) when blocked.
"""

from __future__ import annotations

import re
from typing import Any

import jsonschema
import structlog
from jsonschema import Draft7Validator

from app.core.errors import AppError

logger = structlog.get_logger(__name__)


class GuardrailService:
    def __init__(self) -> None:
        self._regex_rules: list[tuple[str, re.Pattern[str], str]] = []
        self._json_schema: dict[str, Any] | None = None

    def add_regex_rule(self, name: str, pattern: str, action: str = "block") -> None:
        try:
            compiled = re.compile(pattern)
            self._regex_rules.append((name, compiled, action))
            logger.debug("guardrail.regex_rule_added", name=name, pattern=pattern)
        except re.error:
            logger.warning("guardrail.regex_invalid", name=name, pattern=pattern)

    def set_json_schema(self, schema: dict[str, Any]) -> None:
        try:
            Draft7Validator.check_schema(schema)
            self._json_schema = schema
            logger.debug("guardrail.schema_set", schema_keys=list(schema.get("properties", {}).keys()))
        except jsonschema.exceptions.SchemaError:
            logger.warning("guardrail.schema_invalid", error=str(jsonschema.exceptions.SchemaError))
            self._json_schema = None

    def _check_regex(self, text: str | None) -> None:
        if not text:
            return
        for name, pattern, action in self._regex_rules:
            if action != "block":
                continue
            if pattern.search(text):
                raise AppError(422, "content_blocked", f"Content blocked by rule: {name}")

    def validate_input(self, text: str | None) -> None:
        self._check_regex(text)

    def validate_output(self, text: str | None) -> str:
        self._check_regex(text)
        return text or ""

    def rules(self) -> list[dict[str, str]]:
        return [
            {"name": name, "pattern": pattern.pattern, "action": action}
            for name, pattern, action in self._regex_rules
        ]


_guardrail_service: GuardrailService | None = None


def get_guardrail() -> GuardrailService:
    global _guardrail_service
    if _guardrail_service is None:
        _guardrail_service = GuardrailService()
    return _guardrail_service


__all__ = ["GuardrailService", "get_guardrail"]