"""Response models for health endpoints."""

from typing import Literal

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    """Body of ``GET /health/live``.

    ``status`` is a ``Literal`` rather than ``str``. The OpenAPI schema then
    documents the only possible value, and mypy rejects any other string.
    """

    status: Literal["ok"] = "ok"
    version: str


class CheckStatus(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: float
    # Only the error *type* (e.g. "Timeout", "ConnectionRefusedError"), never
    # the message: this endpoint is public, and messages can contain hostnames.
    error: str | None = None


class ReadinessResponse(BaseModel):
    """Body of ``GET /health/ready`` (HTTP 200 when ready, 503 when not)."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckStatus]
