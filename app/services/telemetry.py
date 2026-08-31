"""Telemetry — Prometheus metrics + OpenTelemetry spans.

No-op safe: metrics helpers never raise. OTel span attribute gen_ai.agent.name,
X-Request-ID forwarded into span attributes.
"""

from __future__ import annotations

from typing import Any

import structlog
from opentelemetry import trace
from prometheus_client import Counter, Histogram, generate_latest

logger = structlog.get_logger(__name__)

tracer = trace.get_tracer("demumumind")

llm_tokens = Counter(
    "llm_tokens",
    "LLM tokens processed",
    ["direction", "provider_id", "agent_type"],
)
cost_usd_counter = Counter(
    "cost_usd",
    "Spend in USD",
    ["provider_id", "agent_type"],
)
llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM request latency in seconds",
    ["provider_id"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
requests_total = Counter(
    "requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)


def record_usage(
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    provider_id: str | None = None,
    agent_type: str = "default",
) -> None:
    pid = provider_id or "unknown"
    llm_tokens.labels("in", pid, agent_type).inc(tokens_in)
    llm_tokens.labels("out", pid, agent_type).inc(tokens_out)
    cost_usd_counter.labels(pid, agent_type).inc(cost_usd)


def record_request(method: str, path: str, status: int) -> None:
    requests_total.labels(method, path, str(status)).inc()


def record_latency(seconds: float, provider_id: str | None = None) -> None:
    llm_latency_seconds.labels(provider_id or "unknown").observe(seconds)


def generate_metrics() -> str:
    return generate_latest().decode("utf-8")


def start_span(name: str, request_id: str | None = None, agent_type: str = "default") -> Any:
    span = tracer.start_span(name)
    span.set_attribute("gen_ai.agent.name", agent_type)
    if request_id:
        span.set_attribute("http.request_id", request_id)
    return span


__all__ = [
    "record_usage",
    "record_request",
    "record_latency",
    "generate_metrics",
    "start_span",
    "tracer",
]
