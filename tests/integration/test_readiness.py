"""/health/ready against real Postgres, Redis, Qdrant and SeaweedFS (S3)."""

import time
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.storage.s3 import create_s3_client, ensure_bucket
from tests.integration.conftest import run_alembic

pytestmark = pytest.mark.integration


@pytest.fixture
def ready_settings(db_settings: Settings) -> Iterator[Settings]:
    """Settings for a fully provisioned environment, with a test-only bucket."""
    # S3 bucket names allow lowercase letters, digits, dots and hyphens; no underscores.
    bucket = f"{db_settings.postgres_db.replace('_', '-')}-docs"
    settings = db_settings.model_copy(update={"s3_bucket": bucket})
    s3 = create_s3_client(settings)
    ensure_bucket(s3, settings.s3_bucket)
    yield settings
    s3.delete_bucket(Bucket=settings.s3_bucket)


async def get_ready(app: FastAPI) -> tuple[int, dict[str, object], float]:
    start = time.perf_counter()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/health/ready")
    elapsed = time.perf_counter() - start
    await app.state.engine.dispose()
    await app.state.redis.aclose()
    await app.state.http.aclose()
    return response.status_code, response.json(), elapsed


def statuses(body: dict[str, object]) -> dict[str, str]:
    checks = body["checks"]
    assert isinstance(checks, dict)
    return {name: check["status"] for name, check in checks.items()}


async def test_ready_when_all_dependencies_are_up(ready_settings: Settings) -> None:
    code, body, _ = await get_ready(create_app(ready_settings))

    assert code == 200, body
    assert statuses(body) == {
        "postgres": "ok",
        "redis": "ok",
        "qdrant": "ok",
        "object_storage": "ok",
    }


async def test_unreachable_redis_fails_only_its_check(ready_settings: Settings) -> None:
    # Port 1 has nothing listening: connection refused (a dead or wrong host).
    code, body, elapsed = await get_ready(
        create_app(ready_settings.model_copy(update={"redis_port": 1}))
    )

    assert code == 503
    assert statuses(body)["redis"] == "error"
    assert statuses(body)["postgres"] == "ok"
    assert elapsed < ready_settings.readiness_timeout_seconds + 1


async def test_missing_bucket_fails_object_storage(ready_settings: Settings) -> None:
    code, body, _ = await get_ready(
        create_app(ready_settings.model_copy(update={"s3_bucket": "bucket-that-does-not-exist"}))
    )

    assert code == 503
    assert statuses(body)["object_storage"] == "error"


async def test_wrong_s3_credentials_fail_object_storage(ready_settings: Settings) -> None:
    code, body, _ = await get_ready(
        create_app(ready_settings.model_copy(update={"s3_secret_access_key": SecretStr("wrong")}))
    )

    assert code == 503
    assert statuses(body)["object_storage"] == "error"


async def test_outdated_schema_is_not_ready(ready_settings: Settings) -> None:
    """An API whose code expects newer migrations than the DB has must not take traffic."""
    run_alembic(ready_settings, "downgrade", "base")
    try:
        code, body, _ = await get_ready(create_app(ready_settings))
    finally:
        run_alembic(ready_settings, "upgrade", "head")

    assert code == 503
    checks = body["checks"]
    assert isinstance(checks, dict)
    assert checks["postgres"]["error"] in {"SchemaOutOfDateError", "ProgrammingError"}
