"""Approver groups, HR employee directory, and flexible approval steps.

- approver_groups: named approver sets that fixed workflow steps point to.
- directory_employees / directory_runs: the HR file mirror and its idempotent run ledger.
- memberships.provisioned_by: which accounts the HR sync may deactivate.
- idea_approval_stages: one row per approver task. Rows sharing stage_order form a step;
  assignees may be empty for a skipped step.

Revision ID: 20261118_0031
Revises: 20261118_0030
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261118_0031"
down_revision: str | None = "20261118_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    ]


def _isolate(table: str) -> None:
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_tenant_isolation ON {table}
        USING (tenant_id = app_current_tenant_id())
        WITH CHECK (tenant_id = app_current_tenant_id())
        """
    )


def upgrade() -> None:
    op.create_table(
        "approver_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "member_membership_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("round_robin_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_approver_groups_tenant_name"),
    )
    _isolate("approver_groups")

    op.create_table(
        "directory_employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", sa.String(64), nullable=False),
        sa.Column("first_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("middle_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("location", sa.String(200), nullable=False, server_default=""),
        sa.Column("department", sa.String(200), nullable=False, server_default=""),
        sa.Column("sub_department", sa.String(200), nullable=False, server_default=""),
        sa.Column("manager_employee_id", sa.String(64), nullable=True),
        sa.Column("hod_employee_id", sa.String(64), nullable=True),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("missing_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "tenant_id", "employee_id", name="uq_directory_employees_tenant_employee"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'missing', 'left')", name="ck_directory_employees_status"
        ),
    )
    op.create_index(
        "ix_directory_employees_tenant_email", "directory_employees", ["tenant_id", "email"]
    )
    op.create_index(
        "ix_directory_employees_tenant_status", "directory_employees", ["tenant_id", "status"]
    )
    _isolate("directory_employees")

    op.create_table(
        "directory_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="inbox"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("report", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('previewed', 'applied', 'rejected', 'duplicate', 'failed')",
            name="ck_directory_runs_status",
        ),
    )
    op.create_index("ix_directory_runs_tenant_created", "directory_runs", ["tenant_id", "created_at"])
    op.create_index("ix_directory_runs_tenant_sha", "directory_runs", ["tenant_id", "file_sha256"])
    _isolate("directory_runs")

    op.add_column(
        "memberships",
        sa.Column("provisioned_by", sa.String(24), nullable=False, server_default="manual"),
    )

    op.drop_constraint(
        "uq_idea_approval_stage_round_order", "idea_approval_stages", type_="unique"
    )
    op.create_index(
        "ix_idea_approval_stages_idea_round_order",
        "idea_approval_stages",
        ["idea_id", "round_number", "stage_order"],
    )
    op.add_column(
        "idea_approval_stages",
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "idea_approval_stages",
        sa.Column("completion", sa.String(8), nullable=False, server_default="all"),
    )
    op.add_column("idea_approval_stages", sa.Column("resolution_note", sa.Text(), nullable=True))
    for column in ("assignee_membership_id", "assignee_user_id", "assignee_name", "assignee_email"):
        op.alter_column("idea_approval_stages", column, nullable=True)

    # Existing contracts named one person per stage: express that in the new step format.
    op.execute(
        """
        UPDATE workflow_versions
        SET stages = (
            SELECT jsonb_agg(
                stage
                || jsonb_build_object(
                    'source', 'person',
                    'mode', 'any',
                    'on_unresolved', 'fallback_admin',
                    'skip_if_same_as_previous', false
                )
                ORDER BY position
            )
            FROM jsonb_array_elements(stages) WITH ORDINALITY AS item(stage, position)
        )
        WHERE jsonb_typeof(stages) = 'array' AND jsonb_array_length(stages) > 0
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM idea_approval_stages WHERE assignee_membership_id IS NULL")
    for column in ("assignee_membership_id", "assignee_user_id", "assignee_name", "assignee_email"):
        op.alter_column("idea_approval_stages", column, nullable=False)
    op.drop_column("idea_approval_stages", "resolution_note")
    op.drop_column("idea_approval_stages", "completion")
    op.drop_column("idea_approval_stages", "sequence")
    op.drop_index("ix_idea_approval_stages_idea_round_order", table_name="idea_approval_stages")
    op.create_unique_constraint(
        "uq_idea_approval_stage_round_order",
        "idea_approval_stages",
        ["idea_id", "round_number", "stage_order"],
    )
    op.drop_column("memberships", "provisioned_by")
    op.drop_table("directory_runs")
    op.drop_table("directory_employees")
    op.drop_table("approver_groups")
