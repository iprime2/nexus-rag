"""All ORM models. Importing this package registers every table on ``Base.metadata``.

Alembic's autogenerate compares ``Base.metadata`` with the live database, so a
model that isn't imported here is invisible to migrations.
"""

from app.db.models.api_key import ApiKey
from app.db.models.ingestion import (
    Document,
    DocumentStatus,
    DocumentVersion,
    IngestionBatch,
    IngestionJob,
    IngestionJobEvent,
    VersionStatus,
)
from app.db.models.tenant import Tenant, TenantStatus

__all__ = [
    "ApiKey",
    "Document",
    "DocumentStatus",
    "DocumentVersion",
    "IngestionBatch",
    "IngestionJob",
    "IngestionJobEvent",
    "Tenant",
    "TenantStatus",
    "VersionStatus",
]
