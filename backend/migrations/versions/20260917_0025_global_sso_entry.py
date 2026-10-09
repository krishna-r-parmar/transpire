"""Allow Microsoft SSO to start from the shared sign-in page.

Revision ID: 20260917_0025
Revises: 20260916_0024
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917_0025"
down_revision: str | None = "20260916_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    op.create_index("ix_tenant_sso_configurations_tenant_id", "tenant_sso_configurations", ["tenant_id"])
    op.create_index("ix_external_identities_tenant_id", "external_identities", ["tenant_id"])
    op.create_index("ix_oidc_login_states_tenant_id", "oidc_login_states", ["tenant_id"])
    op.create_index("ix_sso_recovery_tokens_tenant_id", "sso_recovery_tokens", ["tenant_id"])
    op.drop_constraint("uq_external_identity_subject", "external_identities", type_="unique")
    op.create_unique_constraint(
        "uq_external_identity_tenant_subject",
        "external_identities",
        ["tenant_id", "provider", "provider_tenant_id", "subject"],
    )
    op.create_table(
        "global_oidc_login_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_global_oidc_login_states_hash", "global_oidc_login_states", ["state_hash"])
    op.create_index("ix_global_oidc_login_states_expires", "global_oidc_login_states", ["expires_at"])
    op.create_table(
        "sso_workspace_selection_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_tenant_id", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("linked_email", sa.String(length=320), nullable=False),
        sa.Column("allowed_tenant_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_sso_workspace_selection_tokens_hash", "sso_workspace_selection_tokens", ["token_hash"])
    op.execute(
        """
        CREATE FUNCTION resolve_active_sso_workspaces(
            p_directory_id text, p_subject text, p_email text
        )
        RETURNS TABLE (
            tenant_id uuid, slug varchar, name varchar, user_id uuid, membership_id uuid
        )
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT DISTINCT tenants.id, tenants.slug, tenants.name, users.id, memberships.id
            FROM tenant_sso_configurations
            JOIN tenants ON tenants.id = tenant_sso_configurations.tenant_id
            JOIN memberships ON memberships.tenant_id = tenants.id
            JOIN users ON users.id = memberships.user_id
            LEFT JOIN external_identities ON
                external_identities.tenant_id = tenants.id
                AND external_identities.user_id = users.id
                AND external_identities.provider = 'microsoft_entra'
                AND external_identities.provider_tenant_id = p_directory_id
            WHERE tenant_sso_configurations.status = 'active'
              AND tenant_sso_configurations.entra_directory_id = p_directory_id
              AND tenants.status = 'active'
              AND memberships.status = 'active'
              AND (
                  external_identities.subject = p_subject
                  OR lower(users.email) = lower(p_email)
              )
            ORDER BY tenants.name, tenants.id
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_active_sso_workspaces(text, text, text)")
    op.drop_table("sso_workspace_selection_tokens")
    op.drop_table("global_oidc_login_states")
    op.drop_constraint("uq_external_identity_tenant_subject", "external_identities", type_="unique")
    op.create_unique_constraint(
        "uq_external_identity_subject",
        "external_identities",
        ["provider", "provider_tenant_id", "subject"],
    )
    op.drop_index("ix_sso_recovery_tokens_tenant_id", table_name="sso_recovery_tokens")
    op.drop_index("ix_oidc_login_states_tenant_id", table_name="oidc_login_states")
    op.drop_index("ix_external_identities_tenant_id", table_name="external_identities")
    op.drop_index("ix_tenant_sso_configurations_tenant_id", table_name="tenant_sso_configurations")
