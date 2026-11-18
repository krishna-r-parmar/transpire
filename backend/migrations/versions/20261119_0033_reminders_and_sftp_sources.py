"""Overdue approval reminders and per-workspace SFTP sources for the HR report.

Revision ID: 20261119_0033
Revises: 20261118_0032
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261119_0033"
down_revision: str | None = "20261118_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idea_approval_stages",
        sa.Column("reminder_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "idea_approval_stages",
        sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_idea_approval_stages_tenant_overdue",
        "idea_approval_stages",
        ["tenant_id", "status", "due_at"],
    )

    op.create_table(
        "directory_sftp_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("host", sa.String(255), nullable=False, server_default=""),
        sa.Column("port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("username", sa.String(120), nullable=False, server_default=""),
        sa.Column("auth_method", sa.String(16), nullable=False, server_default="password"),
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
        sa.Column("remote_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("trusted_host_key", sa.Text(), nullable=True),
        sa.Column("presented_host_key", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(16), nullable=True),
        sa.Column("last_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", name="uq_directory_sftp_sources_tenant"),
        sa.CheckConstraint(
            "auth_method IN ('password', 'private_key')", name="ck_directory_sftp_auth_method"
        ),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name="ck_directory_sftp_port"),
    )
    op.create_index("ix_directory_sftp_sources_tenant_id", "directory_sftp_sources", ["tenant_id"])
    op.execute("ALTER TABLE directory_sftp_sources ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE directory_sftp_sources FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY directory_sftp_sources_tenant_isolation ON directory_sftp_sources
        USING (tenant_id = app_current_tenant_id())
        WITH CHECK (tenant_id = app_current_tenant_id())
        """
    )


def downgrade() -> None:
    op.drop_table("directory_sftp_sources")
    op.drop_index("ix_idea_approval_stages_tenant_overdue", table_name="idea_approval_stages")
    op.drop_column("idea_approval_stages", "last_reminded_at")
    op.drop_column("idea_approval_stages", "reminder_count")
