"""Failover classification — maps upstream failures to recovery actions.

7 categories: auth, billing, rate_limit, timeout, context_overflow,
model_error, unknown. Decision is deterministic and never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_CONTEXT_HINTS = ("context", "token", "length", "too large", "max_input")
_BILLING_HINTS = ("billing", "quota", "payment", "credit", "insufficient_quota")
_MODEL_HINTS = ("model", "not found", "does not exist", "no such")


@dataclass
class FailoverDecision:
    category: str
    backoff_ms: int = 0
    rotate_key: bool = False
    retry_same_key: bool = False
    message: str = ""
    alert: bool = False
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)


def _contains(body: str, hints: tuple[str, ...]) -> bool:
    lowered = body.lower()
    return any(h in lowered for h in hints)


def classify(status_code: int, body: str) -> FailoverDecision:
    text = body or ""
    if status_code in (401, 403) or "unauthorized" in text or "invalid api key" in text:
        return FailoverDecision(
            category="auth",
            rotate_key=True,
            retry_same_key=False,
            message=f"auth failure ({status_code})",
        )
    if status_code == 402 or _contains(text, _BILLING_HINTS):
        return FailoverDecision(
            category="billing",
            rotate_key=True,
            retry_same_key=False,
            alert=True,
            message=f"billing/quota failure ({status_code})",
        )
    if status_code == 429:
        return FailoverDecision(
            category="rate_limit",
            backoff_ms=500,
            rotate_key=True,
            retry_same_key=True,
            message="rate limited (429)",
        )
    if status_code in (408, 504, 524):
        return FailoverDecision(
            category="timeout",
            backoff_ms=250,
            retry_same_key=True,
            message=f"timeout ({status_code})",
        )
    if status_code == 413 or _contains(text, _CONTEXT_HINTS):
        return FailoverDecision(
            category="context_overflow",
            retry_same_key=True,
            message="context overflow, compact and retry",
        )
    if status_code in (404, 422) or _contains(text, _MODEL_HINTS):
        return FailoverDecision(
            category="model_error",
            retry_same_key=False,
            message="model error, next model in chain",
        )
    return FailoverDecision(
        category="unknown",
        backoff_ms=200,
        retry_same_key=True,
        message=f"unknown error ({status_code})",
    )


def backoff_ms(attempt: int) -> int:
    return int(min(500 * (2**attempt), 30000))


__all__ = ["FailoverDecision", "classify", "backoff_ms"]
