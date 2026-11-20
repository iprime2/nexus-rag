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
