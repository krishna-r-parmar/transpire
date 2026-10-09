"""Add tenant provisioning and invitation boundaries.

Revision ID: 20260818_0006
Revises: 20260818_0005
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0006"
down_revision: str | None = "20260818_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invitation_tokens",
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_invitation_tokens_invited_by_user_id_users",
        "invitation_tokens",
        "users",
        ["invited_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        CREATE FUNCTION ensure_invited_user(p_email text, p_display_name text)
        RETURNS uuid
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        DECLARE
            resolved_user_id uuid;
        BEGIN
            SELECT users.id INTO resolved_user_id
            FROM users
            WHERE lower(users.email) = lower(p_email)
            LIMIT 1;

            IF resolved_user_id IS NULL THEN
                resolved_user_id := gen_random_uuid();
                INSERT INTO users (
                    id, email, display_name, password_hash, is_platform_admin,
                    created_at, updated_at
                ) VALUES (
                    resolved_user_id, lower(p_email), p_display_name, NULL, false,
                    now(), now()
                );
            END IF;
            RETURN resolved_user_id;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION list_platform_tenants()
        RETURNS TABLE (
            tenant_id uuid,
            slug varchar,
            name varchar,
            status tenant_status,
            primary_hostname varchar,
            created_at timestamptz
        )
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT
                tenants.id,
                tenants.slug,
                tenants.name,
                tenants.status,
                primary_domain.hostname,
                tenants.created_at
            FROM tenants
            LEFT JOIN LATERAL (
                SELECT tenant_domains.hostname
                FROM tenant_domains
                WHERE tenant_domains.tenant_id = tenants.id
                  AND tenant_domains.is_primary = true
                ORDER BY tenant_domains.created_at
                LIMIT 1
            ) AS primary_domain ON true
            ORDER BY tenants.created_at DESC
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS list_platform_tenants()")
    op.execute("DROP FUNCTION IF EXISTS ensure_invited_user(text, text)")
    op.drop_constraint(
        "fk_invitation_tokens_invited_by_user_id_users",
        "invitation_tokens",
        type_="foreignkey",
    )
    op.drop_column("invitation_tokens", "invited_by_user_id")
