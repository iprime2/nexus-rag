"""Response model for ``GET /v1/me``."""

import uuid

from pydantic import BaseModel


class MeResponse(BaseModel):
    tenant_id: uuid.UUID
    tenant_slug: str
    api_key_id: uuid.UUID
