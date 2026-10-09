"""Resolve tenant workspaces by shortname instead of hostname.

Revision ID: 20260829_0022
Revises: 20260823_0021
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260829_0022"
down_revision: str | None = "20260823_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION resolve_tenant_by_slug(p_slug text)
        RETURNS TABLE (tenant_id uuid, slug varchar, name varchar, status tenant_status)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT tenants.id, tenants.slug, tenants.name, tenants.status
            FROM tenants
            WHERE lower(tenants.slug) = lower(p_slug)
            LIMIT 1
        $$
        """
    )
    op.execute("DROP FUNCTION list_platform_tenants()")
    op.execute(
        """
        CREATE FUNCTION list_platform_tenants()
        RETURNS TABLE (
            tenant_id uuid,
            slug varchar,
            name varchar,
            status tenant_status,
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
                tenants.created_at
            FROM tenants
            ORDER BY tenants.created_at DESC
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION list_platform_tenants()")
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
    op.execute("DROP FUNCTION IF EXISTS resolve_tenant_by_slug(text)")
