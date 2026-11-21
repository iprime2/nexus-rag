"""Readiness logic without real dependencies: fake probes and fake clients."""

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Environment, Settings
from app.core.readiness import ReadinessCheck, run_checks, s3_probe
from app.main import create_app
from app.storage.s3 import ensure_bucket


async def ok() -> None:
    return None


async def broken() -> None:
    raise ConnectionRefusedError("connect to db.internal.example:5432 failed")  # hostname!


async def hangs() -> None:
    await asyncio.sleep(10)


async def slow() -> None:
    await asyncio.sleep(0.3)


# ------------------------------------------------------------------ runner


async def test_all_ok() -> None:
    results = await run_checks([ReadinessCheck("a", ok), ReadinessCheck("b", ok)], 1.0)

    assert {name: r.status for name, r in results.items()} == {"a": "ok", "b": "ok"}


async def test_failure_reports_error_type_only() -> None:
    [result] = (await run_checks([ReadinessCheck("db", broken)], 1.0)).values()

    assert result.status == "error"
    assert result.error == "ConnectionRefusedError"


async def test_hanging_dependency_times_out_quickly() -> None:
    start = time.perf_counter()
    [result] = (await run_checks([ReadinessCheck("stuck", hangs)], 0.2)).values()

    assert result.error == "Timeout"
    assert time.perf_counter() - start < 1.0


async def test_checks_run_concurrently() -> None:
    start = time.perf_counter()
    await run_checks([ReadinessCheck(f"s{i}", slow) for i in range(4)], 2.0)

    # Four 0.3 s checks: ~0.3 s concurrently, 1.2 s if run one after another.
    assert time.perf_counter() - start < 0.8


# ------------------------------------------------------------------ endpoint


def make_client(*checks: ReadinessCheck) -> AsyncClient:
    app = create_app(Settings(_env_file=None, environment=Environment.TEST))
    app.state.readiness_checks = list(checks)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_ready_returns_200_when_everything_is_ok() -> None:
    async with make_client(ReadinessCheck("postgres", ok), ReadinessCheck("redis", ok)) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["postgres"]["status"] == "ok"


async def test_ready_returns_503_and_does_not_leak_details() -> None:
    async with make_client(
        ReadinessCheck("postgres", broken), ReadinessCheck("redis", ok)
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"] == {
        "status": "error",
        "latency_ms": body["checks"]["postgres"]["latency_ms"],
        "error": "ConnectionRefusedError",
    }
    assert body["checks"]["redis"]["status"] == "ok"
    assert "db.internal.example" not in response.text  # message stays in server logs


async def test_liveness_ignores_dependencies() -> None:
    async with make_client(ReadinessCheck("postgres", broken)) as client:
        assert (await client.get("/health/live")).status_code == 200


# ------------------------------------------------------------------ S3 helpers


class FakeS3:
    def __init__(self, head_error_code: str | None) -> None:
        self.head_error_code = head_error_code
        self.created: list[str] = []

    def head_bucket(self, Bucket: str) -> dict[str, Any]:  # noqa: N803 (boto3's argument name)
        if self.head_error_code:
            raise ClientError({"Error": {"Code": self.head_error_code}}, "HeadBucket")
        return {}

    def create_bucket(self, Bucket: str) -> dict[str, Any]:  # noqa: N803
        self.created.append(Bucket)
        return {}


def test_ensure_bucket_creates_a_missing_bucket() -> None:
    s3 = FakeS3(head_error_code="404")

    assert ensure_bucket(s3, "docs") is True  # type: ignore[arg-type]
    assert s3.created == ["docs"]


def test_ensure_bucket_leaves_an_existing_bucket_alone() -> None:
    s3 = FakeS3(head_error_code=None)

    assert ensure_bucket(s3, "docs") is False  # type: ignore[arg-type]
    assert s3.created == []


def test_ensure_bucket_does_not_hide_permission_errors() -> None:
    with pytest.raises(ClientError):
        ensure_bucket(FakeS3(head_error_code="403"), "docs")  # type: ignore[arg-type]


async def test_s3_probe_runs_blocking_call_in_a_thread() -> None:
    [result] = (
        await run_checks([ReadinessCheck("s3", s3_probe(FakeS3("404"), "docs"))], 1.0)  # type: ignore[arg-type]
    ).values()

    assert result.error == "ClientError"


# ------------------------------------------------------------------ settings


def test_s3_keys_must_come_in_pairs() -> None:
    with pytest.raises(ValidationError, match="NEXUS_S3_SECRET_ACCESS_KEY"):
        Settings(_env_file=None, s3_access_key_id="only-half")  # type: ignore[arg-type]


def test_empty_values_in_dotenv_mean_not_set(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("NEXUS_REDIS_PASSWORD=\nNEXUS_QDRANT_API_KEY=\n")

    settings = Settings(_env_file=env_file)

    assert settings.redis_password is None
    assert settings.qdrant_api_key is None
