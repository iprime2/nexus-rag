"""Database-layer tests that need no running database."""

import time
import uuid

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.ids import _uuid7_fallback, new_id
from app.db.base import Base
from app.db.models import Tenant  # noqa: F401  (registers the table on Base.metadata)
from app.db.session import create_engine

# ------------------------------------------------------------------ IDs


@pytest.mark.parametrize("generate", [new_id, _uuid7_fallback])
def test_ids_are_version_7_rfc_9562(generate: object) -> None:
    value = generate()  # type: ignore[operator]

    assert isinstance(value, uuid.UUID)
    assert value.version == 7
    assert value.variant == uuid.RFC_4122  # the "10" variant bits


def test_ids_sort_by_creation_time() -> None:
    earlier = _uuid7_fallback()
    time.sleep(0.002)  # the timestamp has millisecond resolution
    later = _uuid7_fallback()

    assert earlier < later  # UUIDs compare by their 128-bit value; the timestamp comes first


def test_id_timestamp_matches_the_clock() -> None:
    before_ms = time.time_ns() // 1_000_000
    value = _uuid7_fallback()
    after_ms = time.time_ns() // 1_000_000

    assert before_ms <= value.int >> 80 <= after_ms


def test_ids_are_unique() -> None:
    assert len({_uuid7_fallback() for _ in range(10_000)}) == 10_000


# ------------------------------------------------------------------ settings


def test_database_password_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_POSTGRES_PASSWORD")

    with pytest.raises(ValidationError, match="postgres_password"):
        Settings(_env_file=None)


def test_password_never_appears_in_settings_or_url_output() -> None:
    # Fake secret on purpose: the test proves it never leaks.
    settings = Settings(_env_file=None, postgres_password="s3cr3t-value")  # type: ignore[arg-type]  # noqa: S106

    assert "s3cr3t-value" not in repr(settings)
    assert "s3cr3t-value" not in str(settings.database_url)
    assert "s3cr3t-value" not in repr(settings.database_url)
    # …but the driver still receives the real value.
    assert settings.database_url.password == "s3cr3t-value"  # noqa: S105


def test_database_url_uses_async_psycopg_driver() -> None:
    url = Settings(_env_file=None, postgres_host="db", postgres_port=6543).database_url

    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.database, url.username) == ("db", 6543, "nexus", "nexus")


@pytest.mark.parametrize("field,value", [("postgres_port", 0), ("db_pool_size", 0)])
def test_invalid_database_settings_fail_fast(field: str, value: int) -> None:
    with pytest.raises(ValidationError, match=field):
        # mypy can't type-check a dynamic **kwargs dict against the model fields.
        Settings(_env_file=None, **{field: value})  # type: ignore[arg-type]


# ------------------------------------------------------------------ engine


async def test_engine_uses_configured_pool_and_opens_no_connection() -> None:
    engine = create_engine(Settings(_env_file=None, db_pool_size=3, db_max_overflow=2))
    try:
        assert engine.pool.size() == 3  # type: ignore[attr-defined]
        assert engine.pool.checkedout() == 0  # type: ignore[attr-defined]  # still lazy
    finally:
        await engine.dispose()


# ------------------------------------------------------------------ models


def test_constraints_have_predictable_names() -> None:
    names = {c.name for c in Base.metadata.tables["tenants"].constraints}

    assert {"pk_tenants", "uq_tenants_slug", "ck_tenants_status", "ck_tenants_slug_format"} <= names
