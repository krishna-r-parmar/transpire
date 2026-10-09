"""Allow departments to apply to multiple sites or all sites.

Revision ID: 20260818_0011
Revises: 20260818_0010
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0011"
down_revision: str | None = "20260818_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "configuration_items",
        sa.Column("applies_to_all_sites", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "department_sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["configuration_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["configuration_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "department_id", "site_id", name="uq_department_sites_scope"
        ),
    )
    op.create_index("ix_department_sites_tenant_id", "department_sites", ["tenant_id"])
    op.create_index(
        "ix_department_sites_tenant_department", "department_sites", ["tenant_id", "department_id"]
    )
    op.create_index("ix_department_sites_tenant_site", "department_sites", ["tenant_id", "site_id"])
    op.execute('ALTER TABLE "department_sites" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "department_sites" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "department_sites_tenant_isolation" ON "department_sites" USING (tenant_id = app_current_tenant_id()) WITH CHECK (tenant_id = app_current_tenant_id())'
    )
    op.execute("""
        INSERT INTO department_sites (id, tenant_id, department_id, site_id)
        SELECT gen_random_uuid(), tenant_id, id, parent_id
        FROM configuration_items
        WHERE kind = 'department' AND parent_id IS NOT NULL
        ON CONFLICT (tenant_id, department_id, site_id) DO NOTHING
    """)
    op.execute("UPDATE configuration_items SET parent_id = NULL WHERE kind = 'department'")


def downgrade() -> None:
    op.execute("""
        UPDATE configuration_items AS department
        SET parent_id = scope.site_id
        FROM (
            SELECT DISTINCT ON (department_id) department_id, site_id
            FROM department_sites
            ORDER BY department_id, created_at
        ) AS scope
        WHERE department.id = scope.department_id
    """)
    op.drop_table("department_sites")
    op.drop_column("configuration_items", "applies_to_all_sites")
