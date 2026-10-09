"""Add immutable approval rounds for corrected idea resubmission.

Revision ID: 20260821_0017
Revises: 20260821_0016
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0017"
down_revision: str | None = "20260821_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idea_approval_stages",
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.drop_constraint("uq_idea_approval_stage_order", "idea_approval_stages", type_="unique")
    op.create_unique_constraint(
        "uq_idea_approval_stage_round_order",
        "idea_approval_stages",
        ["idea_id", "round_number", "stage_order"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_idea_approval_stage_round_order", "idea_approval_stages", type_="unique"
    )
    op.create_unique_constraint(
        "uq_idea_approval_stage_order", "idea_approval_stages", ["idea_id", "stage_order"]
    )
    op.drop_column("idea_approval_stages", "round_number")
