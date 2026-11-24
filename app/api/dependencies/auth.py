"""Authentication dependency: ``Authorization: ApiKey <key>`` → ``TenantContext``.

Usage::

    async def handler(tenant: CurrentTenant) -> ...:
        ...  # tenant.tenant_id is trustworthy; it came from the credential

Every failure mode (missing header, malformed key, unknown key, revoked key)
returns the **same** 401, so a caller learns nothing about which keys exist.
"""

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.api.dependencies.db import DbSession
from app.auth.api_keys import parse_authorization_header
from app.auth.service import lookup_api_key
from app.core.tenancy import TenantContext

# Declaring the header as a security scheme adds an "Authorize" button to /docs.
_authorization_header = APIKeyHeader(
    name="Authorization",
    auto_error=False,
    description="`ApiKey <key>`, e.g. `ApiKey nxr_…`",
)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Missing or invalid API key",
    headers={"WWW-Authenticate": "ApiKey"},
)


async def get_tenant_context(
    session: DbSession,
    authorization: Annotated[str | None, Security(_authorization_header)],
) -> TenantContext:
    key = parse_authorization_header(authorization)
    if key is None:
        raise _UNAUTHORIZED

    found = await lookup_api_key(session, key)
    if found is None:
        raise _UNAUTHORIZED
    if not found.tenant_active:
        # The key is valid, so it's safe to tell its holder why access is refused.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant is suspended")

    # Every later log line in this request carries the tenant (never the key).
    structlog.contextvars.bind_contextvars(
        tenant_id=str(found.context.tenant_id), api_key_id=str(found.context.api_key_id)
    )
    return found.context


CurrentTenant = Annotated[TenantContext, Depends(get_tenant_context)]
