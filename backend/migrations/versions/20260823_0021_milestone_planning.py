"""Add milestone planning ownership, dependencies, and evidence.

Revision ID: 20260823_0021
Revises: 20260823_0020
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0021"
down_revision: str | None = "20260823_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_milestones",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "project_milestones",
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "project_milestones",
        sa.Column(
            "dependency_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_foreign_key(
        "fk_project_milestones_owner_user",
        "project_milestones",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_project_milestones_owner_user", "project_milestones", type_="foreignkey"
    )
    op.drop_column("project_milestones", "dependency_ids")
    op.drop_column("project_milestones", "evidence")
    op.drop_column("project_milestones", "owner_user_id")
