"""Typed application configuration.

All configuration comes from environment variables prefixed with ``NEXUS_``
(optionally loaded from a local ``.env`` file). Pydantic validates the values
and converts them to the declared types **once, at startup**. A bad value
therefore stops the process immediately with a clear error, instead of failing
later in the middle of a request.

Settings are added group by group, when the feature that needs them is built
(Postgres in step 1.5, Redis/Qdrant/S3 in 1.6, …). Secrets use
``pydantic.SecretStr``, which prints as ``'**********'`` in logs, reprs and
error messages; the real value comes only from ``.get_secret_value()``.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Process-wide configuration, read from ``NEXUS_*`` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="NEXUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        # Fail on unknown NEXUS_* keys in .env: a typo like NEXUS_DEUBG is an error, not ignored.
        extra="forbid",
        # Settings never change after startup.
        frozen=True,
    )

    environment: Environment = Environment.LOCAL
    debug: bool = False
    docs_enabled: bool = True

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # "json": one JSON object per line, for machines (Docker, CloudWatch, Loki).
    # "console": coloured, human-readable lines, for local development.
    log_format: Literal["json", "console"] = "json"

    # PostgreSQL. Separate fields instead of one URL: the password can be
    # injected on its own (e.g. from AWS Secrets Manager), and it stays a
    # SecretStr so it never appears in logs or error messages.
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "nexus"
    postgres_user: str = "nexus"
    postgres_password: SecretStr  # required: no default, so a missing password fails at startup
    # Connections kept open per process, plus temporary extras under load.
    # Small on purpose: total = processes x (pool + overflow) must stay under
    # Postgres max_connections (see docs/database-design.md §6).
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_pool_timeout_seconds: float = Field(default=10.0, gt=0)

    @property
    def database_url(self) -> URL:
        """SQLAlchemy URL for the async psycopg driver.

        A ``URL`` object (not a string): its ``repr``/``str`` mask the password.
        """
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @model_validator(mode="after")
    def _forbid_unsafe_production_flags(self) -> Self:
        # A cross-field rule: each field is valid on its own, but this combination isn't.
        if self.environment is Environment.PRODUCTION and self.debug:
            raise ValueError("NEXUS_DEBUG must be false when NEXUS_ENVIRONMENT=production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, built on first use and cached afterwards.

    ``lru_cache`` makes this a lazily created singleton (like a NestJS provider
    with the default scope). Tests don't call this; they build ``Settings(...)``
    explicitly and pass it to ``create_app``, so a developer's real ``.env``
    never affects test results.
    """
    return Settings()
