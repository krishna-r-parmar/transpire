"""Charter people as workspace users, and projects opened at approval.

Sponsor and leader become links to users (names stay as snapshots). Every approved idea now
gets its project straight away, in a new "charter_in_progress" status, so it appears in the
Projects portfolio while the charter is drafted. This backfills projects for ideas that are
approved but whose charter has not been submitted yet, and defaults the leader to the submitter.

Revision ID: 20261118_0028
Revises: 20261118_0027
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261118_0028"
down_revision: str | None = "20261118_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _set_tenant(connection: sa.Connection, tenant_id: object) -> None:
    connection.execute(
        sa.text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def upgrade() -> None:
    for column in ("sponsor_user_id", "leader_user_id"):
        op.add_column(
            "project_charters",
            sa.Column(column, postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            f"fk_project_charters_{column}_users",
            "project_charters",
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )

    connection = op.get_bind()
    tenant_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM tenants"))]
    for tenant_id in tenant_ids:
        _set_tenant(connection, tenant_id)
        # The person who submitted the idea leads it unless the charter already names someone.
        connection.execute(
            sa.text(
                """
                UPDATE project_charters AS charter
                SET leader_user_id = ideas.submitter_user_id,
                    leader = CASE WHEN charter.leader = '' THEN users.display_name
                                  ELSE charter.leader END
                FROM ideas JOIN users ON users.id = ideas.submitter_user_id
                WHERE ideas.id = charter.idea_id
                  AND charter.tenant_id = :tenant_id
                  AND charter.leader_user_id IS NULL
                  AND (charter.leader = '' OR charter.leader = users.display_name)
                """
            ),
            {"tenant_id": str(tenant_id)},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO projects (
                    id, tenant_id, idea_id, reference, status, health,
                    active_baseline_version, lead_name, target_completion_date
                )
                SELECT gen_random_uuid(), ideas.tenant_id, ideas.id,
                       regexp_replace(ideas.reference, '^IDEA-', 'PRJ-'),
                       'charter_in_progress', 'not_set', 0,
                       COALESCE(NULLIF(charter.leader, ''), users.display_name),
                       charter.target_completion_date
                FROM ideas
                JOIN project_charters AS charter ON charter.idea_id = ideas.id
                JOIN users ON users.id = ideas.submitter_user_id
                WHERE ideas.tenant_id = :tenant_id
                  AND ideas.status IN ('approved', 'charter_in_progress')
                  AND NOT EXISTS (SELECT 1 FROM projects WHERE projects.idea_id = ideas.id)
                """
            ),
            {"tenant_id": str(tenant_id)},
        )


def downgrade() -> None:
    connection = op.get_bind()
    tenant_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM tenants"))]
    for tenant_id in tenant_ids:
        _set_tenant(connection, tenant_id)
        connection.execute(
            sa.text(
                "DELETE FROM projects WHERE tenant_id = :tenant_id "
                "AND status = 'charter_in_progress'"
            ),
            {"tenant_id": str(tenant_id)},
        )
    for column in ("leader_user_id", "sponsor_user_id"):
        op.drop_constraint(
            f"fk_project_charters_{column}_users", "project_charters", type_="foreignkey"
        )
        op.drop_column("project_charters", column)
