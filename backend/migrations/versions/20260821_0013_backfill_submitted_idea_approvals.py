"""Backfill approval stages for ideas submitted before the runtime existed.

Revision ID: 20260821_0013
Revises: 20260821_0012
Create Date: 2026-08-21
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0013"
down_revision: str | None = "20260821_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    tenant_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM tenants"))]
    for tenant_id in tenant_ids:
        connection.execute(
            sa.text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        submitted = connection.execute(
            sa.text(
                """
                SELECT ideas.id, ideas.tenant_id, ideas.workflow_version_id, workflow_versions.stages
                FROM ideas
                JOIN workflow_versions ON workflow_versions.id = ideas.workflow_version_id
                WHERE ideas.tenant_id = :tenant_id
                  AND ideas.status = 'submitted'
                  AND NOT EXISTS (
                    SELECT 1 FROM idea_approval_stages WHERE idea_id = ideas.id
                  )
                """
            ),
            {"tenant_id": tenant_id},
        ).mappings()
        for idea in submitted:
            fallback = connection.execute(
            sa.text(
                """
                SELECT memberships.id AS membership_id, users.id AS user_id,
                       users.display_name, users.email
                FROM memberships
                JOIN users ON users.id = memberships.user_id
                JOIN membership_roles ON membership_roles.membership_id = memberships.id
                JOIN roles ON roles.id = membership_roles.role_id
                WHERE memberships.tenant_id = :tenant_id
                  AND memberships.status = 'active'
                  AND roles.key = 'tenant_admin'
                ORDER BY users.display_name
                LIMIT 1
                """
            ),
            {"tenant_id": idea["tenant_id"]},
            ).mappings().first()
            if fallback is None:
                continue
            for index, stage in enumerate(idea["stages"] or []):
                assignee = None
                assignee_id = stage.get("assignee_membership_id")
                if assignee_id:
                    assignee = connection.execute(
                    sa.text(
                        """
                        SELECT memberships.id AS membership_id, users.id AS user_id,
                               users.display_name, users.email
                        FROM memberships
                        JOIN users ON users.id = memberships.user_id
                        WHERE memberships.tenant_id = :tenant_id
                          AND memberships.id = :membership_id
                          AND memberships.status IN ('active', 'invited')
                        LIMIT 1
                        """
                    ),
                    {
                        "tenant_id": idea["tenant_id"],
                        "membership_id": uuid.UUID(str(assignee_id)),
                    },
                    ).mappings().first()
                resolved = assignee or fallback
                sla_hours = int(stage.get("sla_hours", 48))
                connection.execute(
                sa.text(
                    """
                    INSERT INTO idea_approval_stages (
                        id, tenant_id, idea_id, stage_order, stage_key, stage_name,
                        assignee_membership_id, assignee_user_id, assignee_name,
                        assignee_email, sla_hours, status, due_at
                    ) VALUES (
                        :id, :tenant_id, :idea_id, :stage_order, :stage_key, :stage_name,
                        :membership_id, :user_id, :display_name, :email, :sla_hours,
                        :status, :due_at
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant_id": idea["tenant_id"],
                    "idea_id": idea["id"],
                    "stage_order": index + 1,
                    "stage_key": str(stage.get("key", f"stage_{index + 1}")),
                    "stage_name": str(stage.get("name", f"Approval stage {index + 1}")),
                    "membership_id": resolved["membership_id"],
                    "user_id": resolved["user_id"],
                    "display_name": resolved["display_name"],
                    "email": resolved["email"],
                    "sla_hours": sla_hours,
                    "status": "pending" if index == 0 else "waiting",
                    "due_at": now + timedelta(hours=sla_hours) if index == 0 else None,
                },
                )


def downgrade() -> None:
    # Rows belong to live approval instances and are intentionally preserved.
    pass
