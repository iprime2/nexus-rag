"""create ingestion tables

Revision ID: 9fb5919e268b
Revises: d24b8df8d995
Create Date: 2026-11-24 05:40:16.288451+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9fb5919e268b"
down_revision: str | Sequence[str] | None = "d24b8df8d995"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default="ACTIVE", nullable=False),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DELETING', 'DELETED')", name=op.f("ck_documents_status")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_documents_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_documents_tenant_id_id")),
    )
    op.create_index(
        "ix_documents_tenant_created",
        "documents",
        ["tenant_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_documents_tenant_external_id_live",
        "documents",
        ["tenant_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_table(
        "ingestion_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ingestion_batches_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_batches")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_ingestion_batches_tenant_id_id")),
    )
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("pipeline_version", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'ACTIVE', 'SUPERSEDED', 'FAILED', 'DELETED')",
            name=op.f("ck_document_versions_status"),
        ),
        sa.CheckConstraint(
            "octet_length(checksum_sha256) = 32", name=op.f("ck_document_versions_checksum_length")
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_document_versions_size_non_negative")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_document_versions_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name=op.f("uq_document_versions_document_id_version_number"),
        ),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_document_versions_tenant_id_id")),
    )
    op.create_index(
        "uq_document_versions_tenant_checksum_live",
        "document_versions",
        ["tenant_id", "checksum_sha256"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('DELETED', 'FAILED')"),
    )
    # documents.current_version_id and document_versions.document_id reference
    # each other, so this key can only be added once both tables exist.
    op.create_foreign_key(
        "fk_documents_current_version",
        "documents",
        "document_versions",
        ["tenant_id", "current_version_id"],
        ["tenant_id", "id"],
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column("checkpoint", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "checkpoint IS NULL OR checkpoint IN ('extract', 'embed')",
            name=op.f("ck_ingestion_jobs_checkpoint"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'QUEUED', 'EXTRACTING', 'CHUNKING', 'CHUNKED', 'EMBEDDING',"
            " 'INDEXING', 'COMPLETED', 'RETRY_PENDING', 'FAILED', 'DEAD_LETTER', 'CANCELLED')",
            name=op.f("ck_ingestion_jobs_status"),
        ),
        sa.CheckConstraint(
            "attempt >= 0 AND max_attempts >= 1", name=op.f("ck_ingestion_jobs_attempts")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["ingestion_batches.tenant_id", "ingestion_batches.id"],
            name="fk_ingestion_jobs_batch",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            name="fk_ingestion_jobs_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_jobs")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_ingestion_jobs_tenant_id_id")),
    )
    op.create_index(
        "ix_ingestion_jobs_status_lease",
        "ingestion_jobs",
        ["status", "lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_ingestion_jobs_status_next_retry",
        "ingestion_jobs",
        ["status", "next_retry_at"],
        unique=False,
    )
    op.create_index(
        "ix_ingestion_jobs_tenant_batch_status",
        "ingestion_jobs",
        ["tenant_id", "batch_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ingestion_jobs_tenant_created",
        "ingestion_jobs",
        ["tenant_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_ingestion_jobs_one_active_per_version",
        "ingestion_jobs",
        ["document_version_id"],
        unique=True,
        postgresql_where=sa.text(
            "status NOT IN ('CANCELLED', 'COMPLETED', 'DEAD_LETTER', 'FAILED')"
        ),
    )
    op.create_table(
        "ingestion_job_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["ingestion_jobs.tenant_id", "ingestion_jobs.id"],
            name="fk_ingestion_job_events_job",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_job_events")),
    )
    op.create_index(
        "ix_ingestion_job_events_job", "ingestion_job_events", ["job_id", "id"], unique=False
    )


def downgrade() -> None:
    # Break the documents <-> document_versions cycle before dropping either table.
    op.drop_constraint("fk_documents_current_version", "documents", type_="foreignkey")
    op.drop_index("ix_ingestion_job_events_job", table_name="ingestion_job_events")
    op.drop_table("ingestion_job_events")
    op.drop_index(
        "uq_ingestion_jobs_one_active_per_version",
        table_name="ingestion_jobs",
        postgresql_where=sa.text(
            "status NOT IN ('CANCELLED', 'COMPLETED', 'DEAD_LETTER', 'FAILED')"
        ),
    )
    op.drop_index("ix_ingestion_jobs_tenant_created", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_tenant_batch_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status_next_retry", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status_lease", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index(
        "uq_document_versions_tenant_checksum_live",
        table_name="document_versions",
        postgresql_where=sa.text("status NOT IN ('DELETED', 'FAILED')"),
    )
    op.drop_table("document_versions")
    op.drop_table("ingestion_batches")
    op.drop_index(
        "uq_documents_tenant_external_id_live",
        table_name="documents",
        postgresql_where=sa.text("external_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.drop_index("ix_documents_tenant_created", table_name="documents")
    op.drop_table("documents")
