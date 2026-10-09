"""Add reliable encrypted email outbox fields.

Revision ID: 20260818_0003
Revises: 20260818_0002
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0003"
down_revision: str | None = "20260818_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "email_deliveries",
        sa.Column("encrypted_template_data", sa.Text(), nullable=True),
    )
    op.add_column(
        "email_deliveries",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "email_deliveries",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_email_deliveries_status_next_attempt",
        "email_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_deliveries_status_next_attempt",
        table_name="email_deliveries",
    )
    op.drop_column("email_deliveries", "locked_at")
    op.drop_column("email_deliveries", "next_attempt_at")
    op.drop_column("email_deliveries", "encrypted_template_data")
