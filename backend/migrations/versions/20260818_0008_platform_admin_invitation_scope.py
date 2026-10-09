"""Limit platform invitation summaries to tenant administrators.

Revision ID: 20260818_0008
Revises: 20260818_0007
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0008"
down_revision: str | None = "20260818_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION list_platform_tenant_invitations()
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
    JOIN membership_roles ON membership_roles.membership_id = memberships.id
    JOIN roles ON roles.id = membership_roles.role_id
    WHERE tokens.accepted_at IS NULL
      AND roles.key = 'tenant_admin'
    ORDER BY tokens.tenant_id, tokens.created_at DESC
$$
"""


def upgrade() -> None:
    op.execute(FUNCTION_SQL)


def downgrade() -> None:
    # Keeping the narrower scope is safe and avoids exposing member invitations.
    op.execute(FUNCTION_SQL)
