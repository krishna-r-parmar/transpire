"""Add membership-aware central sign-in challenges.

Revision ID: 20260829_0023
Revises: 20260829_0022
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260829_0023"
down_revision: str | None = "20260829_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("failed_sign_in_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "global_authentication_throttles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action", "key_hash", name="uq_global_authentication_throttles_scope"
        ),
    )
    op.create_index(
        "ix_global_authentication_throttles_blocked_until",
        "global_authentication_throttles",
        ["blocked_until"],
    )
    op.create_table(
        "workspace_selection_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_workspace_selection_tokens_expires",
        "workspace_selection_tokens",
        ["expires_at"],
    )
    op.execute(
        """
        CREATE FUNCTION lookup_global_sign_in_user(p_email text)
        RETURNS TABLE (
            user_id uuid,
            email varchar,
            display_name varchar,
            password_hash varchar,
            is_platform_admin boolean,
            failed_sign_in_attempts integer,
            locked_until timestamptz
        )
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT
                users.id,
                users.email,
                users.display_name,
                users.password_hash,
                users.is_platform_admin,
                users.failed_sign_in_attempts,
                users.locked_until
            FROM users
            WHERE lower(users.email) = lower(p_email)
            LIMIT 1
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION list_active_user_workspaces(p_user_id uuid)
        RETURNS TABLE (
            membership_id uuid,
            tenant_id uuid,
            slug varchar,
            name varchar
        )
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT memberships.id, tenants.id, tenants.slug, tenants.name
            FROM memberships
            JOIN tenants ON tenants.id = memberships.tenant_id
            WHERE memberships.user_id = p_user_id
              AND memberships.status = 'active'
              AND tenants.status = 'active'
            ORDER BY lower(tenants.name), tenants.id
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS list_active_user_workspaces(uuid)")
    op.execute("DROP FUNCTION IF EXISTS lookup_global_sign_in_user(text)")
    op.drop_table("workspace_selection_tokens")
    op.drop_table("global_authentication_throttles")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_sign_in_attempts")
