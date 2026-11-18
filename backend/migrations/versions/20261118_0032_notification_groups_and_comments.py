"""User group purpose, review comments, and approval email bookkeeping.

Revision ID: 20261118_0032
Revises: 20261118_0031
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261118_0032"
down_revision: str | None = "20261118_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    op.add_column(
        "approver_groups",
        sa.Column("purpose", sa.String(16), nullable=False, server_default="approval"),
    )
    op.create_check_constraint(
        "ck_approver_groups_purpose", "approver_groups", "purpose IN ('approval', 'notification')"
    )

    op.add_column(
        "idea_approval_stages",
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "idea_approval_stages",
        sa.Column("closure_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Work already in flight was assigned before approval emails existed: never back-fill.
    op.execute(
        "UPDATE idea_approval_stages SET notified_at = now() WHERE status = 'pending'"
    )
    op.execute(
        "UPDATE idea_approval_stages SET closure_notified_at = now() WHERE status = 'reassigned'"
    )

    op.create_table(
        "idea_step_consultations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(160), nullable=False),
        sa.Column("user_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "idea_id", "round_number", "stage_order", name="uq_idea_step_consultations_step"
        ),
    )
    _isolate("idea_step_consultations")

    op.create_table(
        "idea_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["idea_comments.id"], ondelete="CASCADE"),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 4000", name="ck_idea_comments_body"),
    )
    op.create_index(
        "ix_idea_comments_tenant_idea", "idea_comments", ["tenant_id", "idea_id", "created_at"]
    )
    _isolate("idea_comments")


def downgrade() -> None:
    op.drop_table("idea_comments")
    op.drop_table("idea_step_consultations")
    op.drop_column("idea_approval_stages", "closure_notified_at")
    op.drop_column("idea_approval_stages", "notified_at")
    op.drop_constraint("ck_approver_groups_purpose", "approver_groups", type_="check")
    op.drop_column("approver_groups", "purpose")
