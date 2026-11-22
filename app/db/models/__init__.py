"""All ORM models. Importing this package registers every table on ``Base.metadata``.

Alembic's autogenerate compares ``Base.metadata`` with the live database, so a
model that isn't imported here is invisible to migrations.
"""

from app.db.models.api_key import ApiKey
from app.db.models.tenant import Tenant, TenantStatus

__all__ = ["ApiKey", "Tenant", "TenantStatus"]
