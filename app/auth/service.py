"""Tenant and API key operations (business logic, no HTTP).

Functions take an ``AsyncSession`` and leave committing to the caller, so one
caller can combine several operations into a single transaction.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.auth.api_keys import display_prefix, generate_api_key, hash_api_key
from app.core.tenancy import TenantContext
from app.db.models import ApiKey, Tenant, TenantStatus


@dataclass(frozen=True)
class IssuedApiKey:
    api_key: ApiKey
    plaintext: str  # shown to the operator once; never stored


@dataclass(frozen=True)
class KeyLookup:
    context: TenantContext
    tenant_active: bool


async def create_tenant(session: AsyncSession, slug: str, name: str) -> Tenant:
    tenant = Tenant(slug=slug, name=name)
    session.add(tenant)
    await session.flush()  # assigns server defaults, surfaces constraint errors now
    return tenant


async def get_tenant_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    tenant: Tenant | None = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    return tenant


async def issue_api_key(session: AsyncSession, tenant_id: uuid.UUID, name: str) -> IssuedApiKey:
    plaintext = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant_id,
        name=name,
        key_prefix=display_prefix(plaintext),
        key_hash=hash_api_key(plaintext),
    )
    session.add(api_key)
    await session.flush()
    return IssuedApiKey(api_key=api_key, plaintext=plaintext)


async def revoke_api_key(session: AsyncSession, key_id: uuid.UUID) -> bool:
    """Revoke a key. Returns False if it doesn't exist or was already revoked."""
    result = await session.execute(
        update(ApiKey)
        .where(ApiKey.id == key_id, ApiKey.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def lookup_api_key(session: AsyncSession, plaintext: str) -> KeyLookup | None:
    """Find the tenant for a presented key. None if unknown or revoked."""
    row = (
        await session.execute(
            select(ApiKey.id, Tenant.id, Tenant.slug, Tenant.status)
            .join(Tenant, Tenant.id == ApiKey.tenant_id)
            .where(ApiKey.key_hash == hash_api_key(plaintext), ApiKey.revoked_at.is_(None))
        )
    ).one_or_none()
    if row is None:
        return None
    key_id, tenant_id, slug, status = row
    return KeyLookup(
        context=TenantContext(tenant_id=tenant_id, tenant_slug=slug, api_key_id=key_id),
        tenant_active=status == TenantStatus.ACTIVE.value,
    )
