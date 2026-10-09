import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        Enum(
            TenantStatus,
            name="tenant_status",
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=TenantStatus.PENDING,
    )
    settings: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    branding: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class LegacyTenantDomain(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Rollback-only hostname mapping; application tenant resolution never reads it."""

    __tablename__ = "tenant_domains"
    __table_args__ = (
        UniqueConstraint("hostname", name="uq_tenant_domains_hostname"),
        Index("ix_tenant_domains_tenant_primary", "tenant_id", "is_primary"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
