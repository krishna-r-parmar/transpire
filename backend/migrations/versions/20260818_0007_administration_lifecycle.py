"""Add invitation and recoverable tenant lifecycle controls.

Revision ID: 20260818_0007
Revises: 20260818_0006
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0007"
down_revision: str | None = "20260818_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE tenant_status ADD VALUE IF NOT EXISTS 'removed'")
    op.add_column(
        "invitation_tokens",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "invitation_tokens",
        sa.Column(
            "last_sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute(
        """
        CREATE FUNCTION list_platform_tenant_invitations()
        RETURNS TABLE (
            tenant_id uuid,
            invitation_id uuid,
            email varchar,
            display_name varchar,
            role_key varchar,
            expires_at timestamptz,
            last_sent_at timestamptz,
            invitation_status text
        )
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT DISTINCT ON (tokens.tenant_id)
                tokens.tenant_id,
                tokens.id,
                tokens.email,
                users.display_name,
                roles.key,
                tokens.expires_at,
                tokens.last_sent_at,
                CASE
                    WHEN tokens.revoked_at IS NOT NULL THEN 'revoked'
                    WHEN tokens.expires_at <= now() THEN 'expired'
                    ELSE 'pending'
                END
            FROM invitation_tokens AS tokens
            JOIN users ON lower(users.email) = lower(tokens.email)
            JOIN memberships
              ON memberships.user_id = users.id
             AND memberships.tenant_id = tokens.tenant_id
            LEFT JOIN membership_roles ON membership_roles.membership_id = memberships.id
            LEFT JOIN roles ON roles.id = membership_roles.role_id
            WHERE tokens.accepted_at IS NULL
            ORDER BY tokens.tenant_id, tokens.created_at DESC
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS list_platform_tenant_invitations()")
    op.drop_column("invitation_tokens", "last_sent_at")
    op.drop_column("invitation_tokens", "revoked_at")
    # PostgreSQL enum values are intentionally retained on downgrade.
