"""Integration-test fixtures: a real Postgres database per test session.

Connection details come from ``NEXUS_*`` environment variables or a local
``.env`` (copy ``.env.example``), pointing at ``docker compose up -d`` services
locally or at service containers in CI. Each
run creates a brand-new database ``nexus_test_<random>``, migrates it with
Alembic (the same migrations production uses), and drops it at the end. Runs
never see each other's data, and the developer's own ``nexus`` database is
never touched.
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.db.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import Environment, Settings
from app.db.base import Base
from app.db.session import create_engine, create_sessionmaker

PROJECT_ROOT = Path(__file__).parents[2]


def alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["configure_logging"] = False  # keep pytest's log capture intact
    return config


def run_alembic(settings: Settings, action: str, revision: str) -> None:
    """Run `alembic upgrade|downgrade <revision>` against the given database."""
    engine = create_sync_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            config = alembic_config()
            config.attributes["connection"] = connection
            getattr(command, action)(config, revision)
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def db_settings() -> Iterator[Settings]:
    base = Settings(environment=Environment.TEST)  # reads env vars and .env, if present
    test_db = f"nexus_test_{uuid.uuid4().hex[:12]}"

    # CREATE/DROP DATABASE can't run inside a transaction, so use AUTOCOMMIT,
    # connected to the default "postgres" maintenance database.
    admin = create_sync_engine(
        base.database_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{test_db}"'))

    settings = base.model_copy(update={"postgres_db": test_db})
    run_alembic(settings, "upgrade", "head")
    try:
        yield settings
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
async def engine(db_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(db_settings)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield create_sessionmaker(engine)
    # Each test leaves empty tables behind. One TRUNCATE over every model table
    # handles foreign keys between them (cheap at this size; revisit when tables grow).
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables}"))
