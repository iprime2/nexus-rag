"""API keys: machine credentials, each belonging to exactly one tenant."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_id
from app.db.base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    # Deleting a tenant deletes its keys; a key never outlives its tenant.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))  # e.g. "ci-uploader"
    key_prefix: Mapped[str] = mapped_column(String(16))  # safe to display
    # SHA-256 of the full key. UNIQUE doubles as the lookup index.
    key_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # never includes the hash
        return f"ApiKey(id={self.id}, prefix={self.key_prefix!r}, tenant_id={self.tenant_id})"
