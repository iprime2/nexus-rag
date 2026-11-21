"""Readiness checks: can this instance serve traffic right now?

Each check is an async function that returns normally when its dependency is
usable and raises otherwise. ``run_checks`` runs them **concurrently**, each
with its own timeout, so the endpoint answers in roughly the time of the
slowest check, bounded by the timeout, never the sum of all checks.

What is reported publicly (the endpoint is unauthenticated):
only the check name, ok/error, latency and the *type* of error. Hostnames,
connection strings and messages go to the server log, not the response.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import httpx
import structlog
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = structlog.get_logger(__name__)

Probe = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    probe: Probe


@dataclass(frozen=True)
class CheckResult:
    status: Literal["ok", "error"]
    latency_ms: float
    error: str | None = None


class DependencyNotReadyError(Exception):
    """The dependency answered, but it is not in a usable state."""


class SchemaOutOfDateError(DependencyNotReadyError):
    """Database migrations are behind (or ahead of) this build."""


async def _run_one(check: ReadinessCheck, per_check_timeout_s: float) -> CheckResult:
    start = time.perf_counter()
    try:
        await asyncio.wait_for(check.probe(), timeout=per_check_timeout_s)
    except Exception as error:  # any failure means "not ready"; never crash the endpoint
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        error_type = "Timeout" if isinstance(error, TimeoutError) else type(error).__name__
        logger.warning(
            "readiness.check_failed", check=check.name, error_type=error_type, error=str(error)
        )
        return CheckResult(status="error", latency_ms=latency_ms, error=error_type)
    return CheckResult(status="ok", latency_ms=round((time.perf_counter() - start) * 1000, 2))


async def run_checks(
    checks: Sequence[ReadinessCheck], per_check_timeout_s: float
) -> dict[str, CheckResult]:
    results = await asyncio.gather(*(_run_one(check, per_check_timeout_s) for check in checks))
    return {check.name: result for check, result in zip(checks, results, strict=True)}


# ---------------------------------------------------------------- probes


def postgres_probe(engine: AsyncEngine, expected_revision: str) -> Probe:
    async def probe() -> None:
        async with engine.connect() as conn:
            current = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        if current != expected_revision:
            raise SchemaOutOfDateError(f"database at {current}, build expects {expected_revision}")

    return probe


def redis_probe(client: Redis) -> Probe:
    async def probe() -> None:
        await client.ping()

    return probe


def qdrant_probe(http: httpx.AsyncClient, base_url: str, api_key: str | None) -> Probe:
    async def probe() -> None:
        headers = {"api-key": api_key} if api_key else {}
        response = await http.get(f"{base_url.rstrip('/')}/readyz", headers=headers)
        if response.status_code != 200:
            raise DependencyNotReadyError(f"qdrant /readyz returned {response.status_code}")

    return probe


def s3_probe(client: "S3Client", bucket: str) -> Probe:
    async def probe() -> None:
        # boto3 is blocking: run it in a worker thread. Note that a timeout here
        # stops *waiting*, but can't cancel the thread; boto3's own connect/read
        # timeouts (app/storage/s3.py) bound how long the thread itself runs.
        await asyncio.to_thread(client.head_bucket, Bucket=bucket)

    return probe
