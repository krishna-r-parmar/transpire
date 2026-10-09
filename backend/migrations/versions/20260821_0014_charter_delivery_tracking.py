"""Add URS action plan and monthly benefit tracking to project charters.

Revision ID: 20260821_0014
Revises: 20260821_0013
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260821_0014"
down_revision: str | None = "20260821_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_charters",
        sa.Column("action_items", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "project_charters",
        sa.Column("monthly_tracking", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("project_charters", "monthly_tracking")
    op.drop_column("project_charters", "action_items")
