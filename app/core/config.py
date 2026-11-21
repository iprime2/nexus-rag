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

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
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
        # `NEXUS_REDIS_PASSWORD=` (empty) means "not set" (None), not an empty password.
        env_ignore_empty=True,
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

    # Redis (Celery broker from Phase 2; rate limits and caches later).
    redis_host: str = "localhost"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_db: int = Field(default=0, ge=0)
    redis_password: SecretStr | None = None  # none locally; managed Redis uses one

    # Qdrant (vector store).
    qdrant_url: AnyHttpUrl = AnyHttpUrl("http://localhost:6333")
    qdrant_api_key: SecretStr | None = None

    # S3-compatible object storage. Leave the endpoint and keys unset on AWS:
    # boto3 then talks to real S3 and takes credentials from the IAM role.
    s3_endpoint_url: AnyHttpUrl | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "nexus-documents"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    # Each dependency check in /health/ready must answer within this time.
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

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

    @model_validator(mode="after")
    def _s3_keys_come_in_pairs(self) -> Self:
        # Half a key pair would silently fall back to other credentials. Reject it instead.
        if (self.s3_access_key_id is None) != (self.s3_secret_access_key is None):
            raise ValueError(
                "Set both NEXUS_S3_ACCESS_KEY_ID and NEXUS_S3_SECRET_ACCESS_KEY, or neither"
            )
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
