"""Add the project execution foundation and immutable charter baselines.

Revision ID: 20260823_0019
Revises: 20260821_0018
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0019"
down_revision: str | None = "20260821_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
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
    )


def _rls(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}" '
        f"USING (tenant_id = app_current_tenant_id()) WITH CHECK (tenant_id = app_current_tenant_id())"
    )


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ready_to_start"),
        sa.Column("health", sa.String(24), nullable=False, server_default="not_set"),
        sa.Column("active_baseline_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lead_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("target_completion_date", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oe_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finance_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idea_id", name="uq_projects_idea"),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_projects_tenant_reference"),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])
    op.create_index(
        "ix_projects_tenant_status", "projects", ["tenant_id", "status", "target_completion_date"]
    )

    op.create_table(
        "project_charter_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default="Initial submitted charter"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version", name="uq_project_charter_baseline_version"),
    )
    op.create_index(
        "ix_project_charter_baselines_tenant_id", "project_charter_baselines", ["tenant_id"]
    )
    op.create_index(
        "ix_project_charter_baselines_tenant_project",
        "project_charter_baselines",
        ["tenant_id", "project_id"],
    )

    op.create_table(
        "project_milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("planned_start", sa.Date(), nullable=True),
        sa.Column("planned_end", sa.Date(), nullable=True),
        sa.Column("actual_start", sa.Date(), nullable=True),
        sa.Column("actual_end", sa.Date(), nullable=True),
        sa.Column("weight", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("progress", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="not_started"),
        sa.Column("completion_criteria", sa.Text(), nullable=False, server_default=""),
        *_timestamps(),
        sa.CheckConstraint("weight >= 0 AND weight <= 100", name="ck_project_milestone_weight"),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100", name="ck_project_milestone_progress"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "position", name="uq_project_milestone_position"),
    )
    op.create_index("ix_project_milestones_tenant_id", "project_milestones", ["tenant_id"])
    op.create_index(
        "ix_project_milestones_tenant_project",
        "project_milestones",
        ["tenant_id", "project_id", "status"],
    )

    op.create_table(
        "project_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("owner_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="not_started"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["milestone_id"], ["project_milestones.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_actions_tenant_id", "project_actions", ["tenant_id"])
    op.create_index(
        "ix_project_actions_tenant_milestone",
        "project_actions",
        ["tenant_id", "milestone_id", "status"],
    )

    op.execute(
        """
        INSERT INTO projects (id, tenant_id, idea_id, reference, status, health,
                              active_baseline_version, lead_name, target_completion_date)
        SELECT gen_random_uuid(), pc.tenant_id, pc.idea_id,
               regexp_replace(i.reference, '^IDEA-', 'PRJ-'),
               'ready_to_start', 'not_set', 1, pc.leader, pc.target_completion_date
        FROM project_charters pc
        JOIN ideas i ON i.id = pc.idea_id
        WHERE pc.submitted_at IS NOT NULL
        """
    )

    op.execute(
        """
        INSERT INTO project_charter_baselines
            (id, tenant_id, project_id, version, snapshot, reason, created_by_user_id, published_at)
        SELECT gen_random_uuid(), p.tenant_id, p.id, 1,
               jsonb_build_object(
                   'sponsor', pc.sponsor, 'leader', pc.leader,
                   'department_id', pc.department_id, 'site_id', pc.site_id,
                   'start_date', pc.start_date, 'target_completion_date', pc.target_completion_date,
                   'team_members', pc.team_members, 'in_scope', pc.in_scope,
                   'out_of_scope', pc.out_of_scope, 'objective', pc.objective,
                   'benefit_type', pc.benefit_type, 'kpi_name', pc.kpi_name,
                   'budget_approved', pc.budget_approved, 'impact_areas', pc.impact_areas,
                   'belt_level', pc.belt_level, 'action_items', pc.action_items,
                   'monthly_tracking', pc.monthly_tracking
               ), 'Initial submitted charter', i.submitter_user_id, pc.submitted_at
        FROM projects p
        JOIN project_charters pc ON pc.idea_id = p.idea_id
        JOIN ideas i ON i.id = p.idea_id
        """
    )

    for table in ("projects", "project_charter_baselines", "project_milestones", "project_actions"):
        _rls(table)


def downgrade() -> None:
    op.drop_table("project_actions")
    op.drop_table("project_milestones")
    op.drop_table("project_charter_baselines")
    op.drop_table("projects")
