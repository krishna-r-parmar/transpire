"""Milestones in the charter, and a baseline on each project milestone.

The charter gains a milestone plan. Each project milestone remembers the due date and weight the
submitted charter promised, plus which milestone marks when benefits start, so re-planning is
recorded as variance instead of overwriting the baseline.

Revision ID: 20261118_0029
Revises: 20261118_0028
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261118_0029"
down_revision: str | None = "20261118_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_charters",
        sa.Column(
            "milestone_plan",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("project_milestones", sa.Column("baseline_planned_end", sa.Date(), nullable=True))
    op.add_column(
        "project_milestones", sa.Column("baseline_weight", sa.Numeric(5, 2), nullable=True)
    )
    op.add_column(
        "project_milestones",
        sa.Column("benefits_start", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("project_milestones", "benefits_start")
    op.drop_column("project_milestones", "baseline_weight")
    op.drop_column("project_milestones", "baseline_planned_end")
    op.drop_column("project_charters", "milestone_plan")
