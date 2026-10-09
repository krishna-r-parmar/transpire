"""Add project team assignments captured by the charter.

Revision ID: 20260823_0020
Revises: 20260823_0019
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0020"
down_revision: str | None = "20260823_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_charters",
        sa.Column(
            "team_membership_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_table(
        "project_team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name_snapshot", sa.String(200), nullable=False),
        sa.Column("email_snapshot", sa.String(320), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="invited"),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "membership_id", name="uq_project_team_membership"),
    )
    op.create_index("ix_project_team_members_tenant_id", "project_team_members", ["tenant_id"])
    op.create_index(
        "ix_project_team_members_tenant_project",
        "project_team_members",
        ["tenant_id", "project_id", "status"],
    )
    op.execute("ALTER TABLE project_team_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_team_members FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY project_team_members_tenant_isolation ON project_team_members
        USING (tenant_id = app_current_tenant_id())
        WITH CHECK (tenant_id = app_current_tenant_id())
        """
    )


def downgrade() -> None:
    op.drop_table("project_team_members")
    op.drop_column("project_charters", "team_membership_ids")
