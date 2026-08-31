"""Failover classification tests — all 7 categories."""

from __future__ import annotations

from app.services.failover import classify


def test_auth_401() -> None:
    d = classify(401, "")
    assert d.category == "auth"
    assert d.rotate_key is True
    assert d.retry_same_key is False


def test_auth_403() -> None:
    d = classify(403, "forbidden")
    assert d.category == "auth"
    assert d.rotate_key is True


def test_billing_402() -> None:
    d = classify(402, "")
    assert d.category == "billing"
    assert d.rotate_key is True
    assert d.alert is True


def test_billing_quota_in_body() -> None:
    d = classify(200, '{"error": {"message": "Insufficient quota"}}')
    assert d.category == "billing"
    assert d.rotate_key is True


def test_rate_limit_429() -> None:
    d = classify(429, "Too many requests")
    assert d.category == "rate_limit"
    assert d.backoff_ms == 500
    assert d.rotate_key is True
    assert d.retry_same_key is True


def test_timeout_504() -> None:
    d = classify(504, "gateway timeout")
    assert d.category == "timeout"
    assert d.retry_same_key is True
    assert d.rotate_key is False


def test_timeout_408() -> None:
    d = classify(408, "")
    assert d.category == "timeout"


def test_context_overflow_413() -> None:
    d = classify(413, "")
    assert d.category == "context_overflow"
    assert d.retry_same_key is True


def test_context_overflow_hint() -> None:
    d = classify(400, '{"error": "maximum context length exceeded"}')
    assert d.category == "context_overflow"


def test_model_error_404() -> None:
    d = classify(404, "model not found")
    assert d.category == "model_error"
    assert d.retry_same_key is False


def test_model_error_422_hint() -> None:
    d = classify(422, '{"error": "The model `x` does not exist"}')
    assert d.category == "model_error"


def test_unknown_500() -> None:
    d = classify(500, "internal")
    assert d.category == "unknown"
    assert d.retry_same_key is True
