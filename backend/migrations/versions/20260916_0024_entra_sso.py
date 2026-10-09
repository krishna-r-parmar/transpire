"""Add Microsoft Entra SSO without changing existing identities.

Revision ID: 20260916_0024
Revises: 20260829_0023
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260916_0024"
down_revision: str | None = "20260829_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("scope", sa.String(length=32), nullable=False, server_default="full"))
    op.add_column("auth_sessions", sa.Column("incident_reference", sa.String(length=160), nullable=True))
    op.create_table(
        "tenant_sso_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entra_directory_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="configured"),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activation_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["validated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_sso_configuration_tenant"),
    )
    op.create_index("ix_tenant_sso_configuration_directory", "tenant_sso_configurations", ["entra_directory_id"])
    op.create_table(
        "external_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="microsoft_entra"),
        sa.Column("provider_tenant_id", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("linked_email", sa.String(length=320), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_tenant_id", "subject", name="uq_external_identity_subject"),
        sa.UniqueConstraint("tenant_id", "user_id", "provider", name="uq_external_identity_tenant_user_provider"),
    )
    op.create_index("ix_external_identities_tenant_user", "external_identities", ["tenant_id", "user_id"])
    op.create_table(
        "oidc_login_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False, server_default="sign_in"),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_oidc_login_states_hash", "oidc_login_states", ["state_hash"])
    op.create_index("ix_oidc_login_states_expires", "oidc_login_states", ["expires_at"])
    op.create_table(
        "sso_recovery_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_reference", sa.String(length=160), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_sso_recovery_tokens_hash", "sso_recovery_tokens", ["token_hash"])
    op.create_index("ix_sso_recovery_tokens_expires", "sso_recovery_tokens", ["expires_at"])

    for table in ("tenant_sso_configurations", "external_identities", "oidc_login_states", "sso_recovery_tokens"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            "USING (tenant_id = app_current_tenant_id()) "
            "WITH CHECK (tenant_id = app_current_tenant_id())"
        )
    op.execute(
        """
        CREATE FUNCTION resolve_tenant_by_id(p_tenant_id uuid)
        RETURNS TABLE (tenant_id uuid, slug varchar, name varchar, status tenant_status)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT tenants.id, tenants.slug, tenants.name, tenants.status
            FROM tenants WHERE tenants.id = p_tenant_id LIMIT 1
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION tenant_requires_sso_global(p_tenant_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM tenant_sso_configurations
                WHERE tenant_id = p_tenant_id AND status = 'active'
            )
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS tenant_requires_sso_global(uuid)")
    op.execute("DROP FUNCTION IF EXISTS resolve_tenant_by_id(uuid)")
    op.drop_table("sso_recovery_tokens")
    op.drop_table("oidc_login_states")
    op.drop_table("external_identities")
    op.drop_table("tenant_sso_configurations")
    op.drop_column("auth_sessions", "incident_reference")
    op.drop_column("auth_sessions", "scope")
