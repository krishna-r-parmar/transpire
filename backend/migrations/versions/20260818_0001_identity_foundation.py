"""Create tenant, identity, and communications foundations.

Revision ID: 20260818_0001
Revises:
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

tenant_status = postgresql.ENUM(
    "pending",
    "active",
    "suspended",
    name="tenant_status",
    create_type=False,
)
membership_status = postgresql.ENUM(
    "invited",
    "active",
    "inactive",
    "locked",
    name="membership_status",
    create_type=False,
)
email_delivery_status = postgresql.ENUM(
    "queued",
    "sending",
    "sent",
    "failed",
    name="email_delivery_status",
    create_type=False,
)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def _enable_tenant_rls(table_name: str, *, force: bool = True) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    if force:
        op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}" '
            "USING (tenant_id = app_current_tenant_id()) "
            "WITH CHECK (tenant_id = app_current_tenant_id())"
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    tenant_status.create(bind, checkfirst=True)
    membership_status.create(bind, checkfirst=True)
    email_delivery_status.create(bind, checkfirst=True)

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", tenant_status, nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "branding",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "tenant_domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hostname", name="uq_tenant_domains_hostname"),
    )
    op.create_index(
        "ix_tenant_domains_tenant_primary",
        "tenant_domains",
        ["tenant_id", "is_primary"],
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", membership_status, nullable=False),
        sa.Column("employee_number", sa.String(length=80), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])
    op.create_index("ix_memberships_tenant_status", "memberships", ["tenant_id", "status"])

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_roles_tenant_key"),
    )
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])

    op.create_table(
        "membership_roles",
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("membership_id", "role_id"),
    )

    for table_name, token_table in (
        ("auth_sessions", False),
        ("password_reset_tokens", True),
    ):
        token_columns: list[sa.Column] = [
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("token_hash", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        ]
        token_columns.append(
            sa.Column(
                "consumed_at" if token_table else "revoked_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        op.create_table(
            table_name,
            *token_columns,
            *_timestamps(),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index(f"ix_{table_name}_tenant_id", table_name, ["tenant_id"])

    op.create_index(
        "ix_auth_sessions_tenant_user",
        "auth_sessions",
        ["tenant_id", "user_id"],
    )
    op.create_index(
        "ix_password_reset_tenant_user",
        "password_reset_tokens",
        ["tenant_id", "user_id"],
    )

    op.create_table(
        "invitation_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_invitation_tokens_tenant_id", "invitation_tokens", ["tenant_id"])
    op.create_index(
        "ix_invitation_tokens_tenant_email",
        "invitation_tokens",
        ["tenant_id", "email"],
    )

    op.create_table(
        "email_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=250), nullable=False),
        sa.Column(
            "template_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", email_delivery_status, nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_deliveries_tenant_id", "email_deliveries", ["tenant_id"])
    op.create_index(
        "ix_email_deliveries_tenant_status",
        "email_deliveries",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_email_deliveries_tenant_recipient",
        "email_deliveries",
        ["tenant_id", "recipient"],
    )

    op.execute(
        """
        CREATE FUNCTION app_current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$
            SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
        $$
        """
    )

    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenants_tenant_isolation ON tenants
        USING (id = app_current_tenant_id())
        WITH CHECK (id = app_current_tenant_id())
        """
    )
    _enable_tenant_rls("tenant_domains", force=False)
    for table_name in (
        "memberships",
        "roles",
        "auth_sessions",
        "password_reset_tokens",
        "invitation_tokens",
        "email_deliveries",
    ):
        _enable_tenant_rls(table_name)

    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY users_tenant_select ON users FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM memberships
                WHERE memberships.user_id = users.id
                  AND memberships.tenant_id = app_current_tenant_id()
            )
        )
        """
    )
    op.execute("CREATE POLICY users_insert ON users FOR INSERT WITH CHECK (true)")
    op.execute(
        """
        CREATE POLICY users_tenant_update ON users FOR UPDATE
        USING (
            EXISTS (
                SELECT 1 FROM memberships
                WHERE memberships.user_id = users.id
                  AND memberships.tenant_id = app_current_tenant_id()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM memberships
                WHERE memberships.user_id = users.id
                  AND memberships.tenant_id = app_current_tenant_id()
            )
        )
        """
    )

    op.execute("ALTER TABLE membership_roles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE membership_roles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY membership_roles_tenant_isolation ON membership_roles
        USING (
            EXISTS (
                SELECT 1 FROM memberships
                WHERE memberships.id = membership_roles.membership_id
                  AND memberships.tenant_id = app_current_tenant_id()
            )
            AND EXISTS (
                SELECT 1 FROM roles
                WHERE roles.id = membership_roles.role_id
                  AND roles.tenant_id = app_current_tenant_id()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM memberships
                WHERE memberships.id = membership_roles.membership_id
                  AND memberships.tenant_id = app_current_tenant_id()
            )
            AND EXISTS (
                SELECT 1 FROM roles
                WHERE roles.id = membership_roles.role_id
                  AND roles.tenant_id = app_current_tenant_id()
            )
        )
        """
    )

    op.execute(
        """
        CREATE FUNCTION resolve_tenant_by_hostname(p_hostname text)
        RETURNS TABLE (tenant_id uuid, slug varchar, name varchar, status tenant_status)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT tenants.id, tenants.slug, tenants.name, tenants.status
            FROM tenant_domains
            JOIN tenants ON tenants.id = tenant_domains.tenant_id
            WHERE lower(tenant_domains.hostname) = lower(p_hostname)
              AND tenant_domains.is_verified = true
            LIMIT 1
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_tenant_by_hostname(text)")

    for table_name in (
        "email_deliveries",
        "invitation_tokens",
        "password_reset_tokens",
        "auth_sessions",
        "membership_roles",
        "roles",
        "memberships",
        "users",
        "tenant_domains",
        "tenants",
    ):
        op.drop_table(table_name)

    op.execute("DROP FUNCTION IF EXISTS app_current_tenant_id()")
    email_delivery_status.drop(op.get_bind(), checkfirst=True)
    membership_status.drop(op.get_bind(), checkfirst=True)
    tenant_status.drop(op.get_bind(), checkfirst=True)
