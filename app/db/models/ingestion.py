"""Ingestion tables (docs/database-design.md): batches, documents, versions, jobs, job events.

Patterns used throughout:

* ``tenant_id`` on every table (D-1), and **composite foreign keys**
  ``(tenant_id, parent_id) → parent(tenant_id, id)``. The database itself
  then refuses a row that points at another tenant's parent, whatever the
  application code does. Each parent therefore has ``UNIQUE (tenant_id, id)``
  as the target for those keys.
* Status columns are ``text`` + ``CHECK`` built from the Python enums (D-5),
  so the allowed values are defined once.
* **Partial unique indexes** encode business rules the database must
  guarantee under concurrency: one live document per ``external_id``, one live
  version per checksum (dedupe), one active job per version.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_id
from app.db.base import Base
from app.ingestion.state import TERMINAL_STATES, Checkpoint, JobStatus


def _in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


def _not_in(column: str, values: set[str] | frozenset[Any]) -> str:
    listed = ", ".join(f"'{v}'" for v in sorted(str(v) for v in values))
    return f"{column} NOT IN ({listed})"


class DocumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELETING = "DELETING"  # hidden from retrieval, cleanup in progress
    DELETED = "DELETED"  # tombstone kept for audit


class VersionStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    ACTIVE = "ACTIVE"  # the current, searchable version
    SUPERSEDED = "SUPERSEDED"  # replaced by a newer version
    FAILED = "FAILED"
    DELETED = "DELETED"


_TIMESTAMP = DateTime(timezone=True)


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, server_default=func.now())
    # Set when the client says "no more uploads", so "batch complete" is well-defined.
    sealed_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)


class Document(Base):
    """The logical document a user searches and deletes ("Travel Policy")."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(_in("status", DocumentStatus), name="status"),
        # `current_version_id` and `document_versions.document_id` point at each
        # other, so this FK is added after both tables exist (use_alter).
        ForeignKeyConstraint(
            ["tenant_id", "current_version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            name="fk_documents_current_version",
            use_alter=True,
        ),
        # A client-supplied identity (assumption A-1) is unique per tenant among
        # live documents; deleting a document frees its external_id.
        Index(
            "uq_documents_tenant_external_id_live",
            "tenant_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("ix_documents_tenant_created", "tenant_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(
        Text, default=DocumentStatus.ACTIVE.value, server_default=DocumentStatus.ACTIVE.value
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]")
    )
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)


class DocumentVersion(Base):
    """One immutable upload of a document's bytes. Jobs, chunks and vectors belong to a version."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("document_id", "version_number"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_document_versions_document",
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("status", VersionStatus), name="status"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        CheckConstraint("octet_length(checksum_sha256) = 32", name="checksum_length"),
        # Dedupe: the same bytes can't be registered twice in a tenant while live.
        # Concurrent uploads of one file race on this index; exactly one insert wins.
        Index(
            "uq_document_versions_tenant_checksum_live",
            "tenant_id",
            "checksum_sha256",
            unique=True,
            postgresql_where=text("status NOT IN ('DELETED', 'FAILED')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    version_number: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[bytes] = mapped_column(LargeBinary(32))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, default=VersionStatus.PENDING.value, server_default=VersionStatus.PENDING.value
    )
    page_count: Mapped[int | None] = mapped_column(Integer)
    # How the version was processed, so we know what to re-index after a change.
    pipeline_version: Mapped[str | None] = mapped_column(Text)
    embedding_model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, server_default=func.now())
    indexed_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)


class IngestionJob(Base):
    """One processing run of a document version through the pipeline."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            name="fk_ingestion_jobs_version",
            ondelete="CASCADE",
        ),
        # No ON DELETE SET NULL here: on a composite key it would also null
        # tenant_id. Batches with jobs simply can't be deleted.
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["ingestion_batches.tenant_id", "ingestion_batches.id"],
            name="fk_ingestion_jobs_batch",
        ),
        CheckConstraint(_in("status", JobStatus), name="status"),
        CheckConstraint(
            f"checkpoint IS NULL OR {_in('checkpoint', Checkpoint)}", name="checkpoint"
        ),
        CheckConstraint("attempt >= 0 AND max_attempts >= 1", name="attempts"),
        # At most one non-terminal job per version: a duplicate submission is
        # rejected by the database, not by a check-then-insert in Python.
        Index(
            "uq_ingestion_jobs_one_active_per_version",
            "document_version_id",
            unique=True,
            postgresql_where=text(_not_in("status", TERMINAL_STATES)),
        ),
        # Sweeper scans (docs/ingestion-workflow.md §4).
        Index("ix_ingestion_jobs_status_lease", "status", "lease_expires_at"),
        Index("ix_ingestion_jobs_status_next_retry", "status", "next_retry_at"),
        # Batch progress and listings.
        Index("ix_ingestion_jobs_tenant_batch_status", "tenant_id", "batch_id", "status"),
        Index("ix_ingestion_jobs_tenant_created", "tenant_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    document_version_id: Mapped[uuid.UUID] = mapped_column()
    batch_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(
        Text, default=JobStatus.PENDING.value, server_default=JobStatus.PENDING.value
    )
    checkpoint: Mapped[str | None] = mapped_column(Text)
    # Incremented on every claim; doubles as the fencing token for worker writes.
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)
    next_retry_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )
    queued_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)
    started_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)
    completed_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)


class IngestionJobEvent(Base):
    """Append-only log of every state transition: a timeline per job, and stage metrics."""

    __tablename__ = "ingestion_job_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["ingestion_jobs.tenant_id", "ingestion_jobs.id"],
            name="fk_ingestion_job_events_job",
            ondelete="CASCADE",
        ),
        Index("ix_ingestion_job_events_job", "job_id", "id"),
    )

    # A sequence-backed bigint: events are ordered by insertion, and the key is cheap.
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    job_id: Mapped[uuid.UUID] = mapped_column()
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, server_default=func.now())
