"""Add approval runtime, employee home work queue, and project charters.

Revision ID: 20260821_0012
Revises: 20260818_0011
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260821_0012"
down_revision: str | None = "20260818_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def _rls(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}" USING (tenant_id = app_current_tenant_id()) WITH CHECK (tenant_id = app_current_tenant_id())'
    )


def upgrade() -> None:
    for value in (
        "needs_correction",
        "rejected",
        "approved",
        "charter_in_progress",
        "charter_submitted",
    ):
        op.execute(f"ALTER TYPE idea_status ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "idea_approval_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("stage_key", sa.String(80), nullable=False),
        sa.Column("stage_name", sa.String(160), nullable=False),
        sa.Column("assignee_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignee_name", sa.String(200), nullable=False),
        sa.Column("assignee_email", sa.String(320), nullable=False),
        sa.Column("sla_hours", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("status", sa.String(32), nullable=False, server_default="waiting"),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actioned_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_membership_id"], ["memberships.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idea_id", "stage_order", name="uq_idea_approval_stage_order"),
    )
    op.create_index("ix_idea_approval_stages_tenant_id", "idea_approval_stages", ["tenant_id"])
    op.create_index(
        "ix_idea_approval_stages_tenant_assignee",
        "idea_approval_stages",
        ["tenant_id", "assignee_user_id", "status"],
    )
    op.create_index(
        "ix_idea_approval_stages_tenant_idea",
        "idea_approval_stages",
        ["tenant_id", "idea_id"],
    )

    op.create_table(
        "project_charters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sponsor", sa.String(200), nullable=False, server_default=""),
        sa.Column("leader", sa.String(200), nullable=False, server_default=""),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_completion_date", sa.Date(), nullable=True),
        sa.Column("team_members", postgresql.ARRAY(sa.String(200)), nullable=False, server_default="{}"),
        sa.Column("in_scope", sa.Text(), nullable=False, server_default=""),
        sa.Column("out_of_scope", sa.Text(), nullable=False, server_default=""),
        sa.Column("objective", sa.Text(), nullable=False, server_default=""),
        sa.Column("benefit_type", sa.String(40), nullable=False, server_default="cost_saving"),
        sa.Column("kpi_name", sa.String(160), nullable=False, server_default=""),
        sa.Column("budget_approved", sa.Numeric(16, 2), nullable=True),
        sa.Column("impact_areas", postgresql.ARRAY(sa.String(24)), nullable=False, server_default="{}"),
        sa.Column("belt_level", sa.String(40), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["configuration_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["configuration_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idea_id", name="uq_project_charters_idea"),
    )
    op.create_index("ix_project_charters_tenant_id", "project_charters", ["tenant_id"])
    op.create_index(
        "ix_project_charters_tenant_idea", "project_charters", ["tenant_id", "idea_id"]
    )

    _rls("idea_approval_stages")
    _rls("project_charters")


def downgrade() -> None:
    op.drop_table("project_charters")
    op.drop_table("idea_approval_stages")
    # PostgreSQL enum values remain intentionally available. Removing them safely
    # would require recreating the shared type and rewriting existing idea rows.
