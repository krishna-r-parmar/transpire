import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DirectoryEmployee(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    """One employee as last reported by the HR system, keyed by HR employee ID."""

    __tablename__ = "directory_employees"
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_id", name="uq_directory_employees_tenant_employee"),
        Index("ix_directory_employees_tenant_email", "tenant_id", "email"),
        Index("ix_directory_employees_tenant_status", "tenant_id", "status"),
    )

    employee_id: Mapped[str] = mapped_column(String(64), nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    middle_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    location: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    department: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    sub_department: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    manager_employee_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hod_employee_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 of the normalised HR fields; unchanged rows are skipped on every run.
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # active: in the latest file. missing: absent from the latest file (grace period).
    # left: absent for consecutive runs, access removed.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    missing_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DirectoryRun(UUIDPrimaryKeyMixin, TenantOwnedMixin, Base):
    """One processed HR file: the ledger that makes ingestion idempotent and auditable."""

    __tablename__ = "directory_runs"
    __table_args__ = (
        Index("ix_directory_runs_tenant_created", "tenant_id", "created_at"),
        Index("ix_directory_runs_tenant_sha", "tenant_id", "file_sha256"),
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="inbox")
    # previewed | applied | rejected | duplicate | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    report: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DirectorySftpSource(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    """Where TRANSPIRE fetches this workspace's HR report from.

    The password or private key is encrypted at rest and never returned to the browser.
    ``trusted_host_key`` is the server's public key an Owner confirmed; every connection
    verifies it before sending credentials. ``presented_host_key`` is the key seen by the
    last "check server", awaiting that confirmation.
    """

    __tablename__ = "directory_sftp_sources"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_directory_sftp_sources_tenant"),)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    username: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    auth_method: Mapped[str] = mapped_column(String(16), nullable=False, default="password")
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    trusted_host_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    presented_host_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
