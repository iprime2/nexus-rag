"""``GET /v1/me``: who am I? Useful for clients to verify their key and tenant."""

from fastapi import APIRouter

from app.api.dependencies.auth import CurrentTenant
from app.api.schemas.me import MeResponse

router = APIRouter(prefix="/v1", tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def me(tenant: CurrentTenant) -> MeResponse:
    return MeResponse(
        tenant_id=tenant.tenant_id, tenant_slug=tenant.tenant_slug, api_key_id=tenant.api_key_id
    )
