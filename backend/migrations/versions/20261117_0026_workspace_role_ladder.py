"""Introduce the four-step workspace role ladder.

Viewer, Contributor (idea_submitter), Workspace Admin (tenant_admin) and Workspace Owner.
Existing Tenant Administrators become Workspace Owners so nobody loses access, and every
membership is collapsed to its single highest role.

Revision ID: 20261117_0026
Revises: 20260917_0025
Create Date: 2026-11-17
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261117_0026"
down_revision: str | None = "20260917_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of app.domains.identity.access at the time of this revision.
_CONTRIBUTE = ["idea.view", "idea.create", "project.contribute", "approval.act"]
_ADMINISTER = [
    "idea.view_all",
    "project.view_all",
    "audit.view_all",
    "tenant.settings.manage",
    "workflow.publish",
    "tenant.people.manage",
]
ROLES = [
    ("viewer", "Viewer", 0, ["idea.view"]),
    ("idea_submitter", "Contributor", 1, _CONTRIBUTE),
    ("tenant_admin", "Workspace Admin", 2, _CONTRIBUTE + _ADMINISTER),
    (
        "workspace_owner",
        "Workspace Owner",
        3,
        _CONTRIBUTE + _ADMINISTER + ["tenant.roles.manage", "tenant.security.manage"],
    ),
]

LEGACY_ROLES = [
    (
        "tenant_admin",
        "Tenant Administrator",
        ["idea.create", "idea.view", "tenant.people.manage", "tenant.settings.manage"],
    ),
    ("idea_submitter", "Idea Submitter", ["idea.create", "idea.view"]),
]


def _invitation_function(admin_keys: str) -> str:
    return f"""
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
      AND roles.key IN ({admin_keys})
    ORDER BY tokens.tenant_id, tokens.created_at DESC
$$
"""


def _set_tenant(connection: sa.Connection, tenant_id: object) -> None:
    connection.execute(
        sa.text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def _upsert_role(
    connection: sa.Connection, tenant_id: object, key: str, name: str, permissions: list[str]
) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO roles (id, tenant_id, key, name, permissions, is_system)
            VALUES (gen_random_uuid(), :tenant_id, :key, :name, CAST(:permissions AS jsonb), true)
            ON CONFLICT ON CONSTRAINT uq_roles_tenant_key
            DO UPDATE SET name = EXCLUDED.name,
                          permissions = EXCLUDED.permissions,
                          is_system = true,
                          updated_at = now()
            """
        ),
        {"tenant_id": tenant_id, "key": key, "name": name, "permissions": json.dumps(permissions)},
    )


def _move_role(connection: sa.Connection, tenant_id: object, source: str, target: str) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE membership_roles
            SET role_id = (SELECT id FROM roles WHERE tenant_id = :tenant_id AND key = :target)
            WHERE role_id = (SELECT id FROM roles WHERE tenant_id = :tenant_id AND key = :source)
              AND NOT EXISTS (
                SELECT 1 FROM membership_roles AS existing
                WHERE existing.membership_id = membership_roles.membership_id
                  AND existing.role_id = (
                    SELECT id FROM roles WHERE tenant_id = :tenant_id AND key = :target
                  )
              )
            """
        ),
        {"tenant_id": tenant_id, "source": source, "target": target},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM membership_roles
            WHERE role_id = (SELECT id FROM roles WHERE tenant_id = :tenant_id AND key = :source)
            """
        ),
        {"tenant_id": tenant_id, "source": source},
    )


def upgrade() -> None:
    connection = op.get_bind()
    tenant_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM tenants"))]
    ranks = ", ".join(f"('{key}', {rank})" for key, _, rank, _ in ROLES)
    for tenant_id in tenant_ids:
        _set_tenant(connection, tenant_id)
        for key, name, _, permissions in ROLES:
            _upsert_role(connection, tenant_id, key, name, permissions)
        _move_role(connection, tenant_id, "tenant_admin", "workspace_owner")
        # One role per membership: keep only the highest-ranked ladder role.
        connection.execute(
            sa.text(
                f"""
                WITH ladder(key, rank) AS (VALUES {ranks}),
                ranked AS (
                    SELECT membership_roles.membership_id, membership_roles.role_id,
                           row_number() OVER (
                               PARTITION BY membership_roles.membership_id
                               ORDER BY ladder.rank DESC NULLS LAST
                           ) AS position
                    FROM membership_roles
                    JOIN roles ON roles.id = membership_roles.role_id
                    LEFT JOIN ladder ON ladder.key = roles.key
                    WHERE roles.tenant_id = :tenant_id
                )
                DELETE FROM membership_roles
                USING ranked
                WHERE membership_roles.membership_id = ranked.membership_id
                  AND membership_roles.role_id = ranked.role_id
                  AND ranked.position > 1
                """
            ),
            {"tenant_id": tenant_id},
        )
    op.execute(_invitation_function("'tenant_admin', 'workspace_owner'"))


def downgrade() -> None:
    connection = op.get_bind()
    tenant_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM tenants"))]
    for tenant_id in tenant_ids:
        _set_tenant(connection, tenant_id)
        _move_role(connection, tenant_id, "workspace_owner", "tenant_admin")
        _move_role(connection, tenant_id, "viewer", "idea_submitter")
        connection.execute(
            sa.text(
                "DELETE FROM roles WHERE tenant_id = :tenant_id "
                "AND key IN ('viewer', 'workspace_owner')"
            ),
            {"tenant_id": tenant_id},
        )
        for key, name, permissions in LEGACY_ROLES:
            _upsert_role(connection, tenant_id, key, name, permissions)
    op.execute(_invitation_function("'tenant_admin'"))
