"""Add authentication throttling and temporary account lockouts.

Revision ID: 20260818_0005
Revises: 20260818_0004
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0005"
down_revision: str | None = "20260818_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column("failed_sign_in_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "memberships",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "authentication_throttles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "action",
            "key_hash",
            name="uq_authentication_throttles_scope",
        ),
    )
    op.create_index(
        "ix_authentication_throttles_tenant_id",
        "authentication_throttles",
        ["tenant_id"],
    )
    op.create_index(
        "ix_authentication_throttles_blocked_until",
        "authentication_throttles",
        ["blocked_until"],
    )
    op.execute("ALTER TABLE authentication_throttles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE authentication_throttles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY authentication_throttles_tenant_isolation
        ON authentication_throttles
        USING (tenant_id = app_current_tenant_id())
        WITH CHECK (tenant_id = app_current_tenant_id())
        """
    )


def downgrade() -> None:
    op.drop_table("authentication_throttles")
    op.drop_column("memberships", "locked_until")
    op.drop_column("memberships", "failed_sign_in_attempts")
