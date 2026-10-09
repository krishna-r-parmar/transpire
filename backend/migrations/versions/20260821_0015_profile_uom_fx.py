"""Add user profile preferences, measurement units, and FX snapshots.

Revision ID: 20260821_0015
Revises: 20260821_0014
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260821_0015"
down_revision: str | None = "20260821_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("profile_settings", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("ideas", sa.Column("baseline_uom", sa.String(length=40), nullable=False, server_default=""))
    op.add_column("ideas", sa.Column("target_uom", sa.String(length=40), nullable=False, server_default=""))
    op.add_column("ideas", sa.Column("usd_exchange_rate", sa.Numeric(18, 8), nullable=True))
    op.add_column("ideas", sa.Column("fx_rate_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("ideas", "fx_rate_date")
    op.drop_column("ideas", "usd_exchange_rate")
    op.drop_column("ideas", "target_uom")
    op.drop_column("ideas", "baseline_uom")
    op.drop_column("users", "profile_settings")
