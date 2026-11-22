"""The caller's tenant, resolved from their credential.

Every tenant-scoped operation receives a ``TenantContext``. It is produced
**only** by the authentication dependency, never from request bodies, query
strings or path parameters, so a caller cannot ask for another tenant's data
by changing an ID in the request (ADR-0008).
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: uuid.UUID
    tenant_slug: str
    api_key_id: uuid.UUID
