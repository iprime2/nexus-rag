"""Tenant: the isolation boundary. Every tenant-owned row will reference one.

Only this table exists in Phase 1. The other tables arrive with the features
that need them (docs/database-design.md).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_id
from app.db.base import Base


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        # text + CHECK instead of a native Postgres ENUM (decision D-5):
        # changing the allowed values is an ordinary migration.
        CheckConstraint("status IN ('active', 'suspended')", name="status"),
        # A slug appears in URLs and login: lowercase letters, digits, single hyphens.
        CheckConstraint(r"slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(63), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        Text, default=TenantStatus.ACTIVE.value, server_default=TenantStatus.ACTIVE.value
    )
    # Full-text-search language for this tenant's documents (assumption A-4).
    fts_config: Mapped[str] = mapped_column(Text, default="english", server_default="english")
    # Timestamps come from the database clock (one clock for all API replicas and workers).
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"Tenant(id={self.id}, slug={self.slug!r}, status={self.status!r})"
