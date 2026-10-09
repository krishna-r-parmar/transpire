"""Add tenant master data and versioned workflow contracts.

Revision ID: 20260818_0009
Revises: 20260818_0008
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0009"
down_revision: str | None = "20260818_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

workflow_status = postgresql.ENUM(
    "draft", "published", "retired", name="workflow_version_status", create_type=False
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


def _rls(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}" USING (tenant_id = app_current_tenant_id()) WITH CHECK (tenant_id = app_current_tenant_id())'
    )


def upgrade() -> None:
    workflow_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "configuration_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["configuration_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "kind", "code", name="uq_configuration_items_tenant_kind_code"
        ),
    )
    op.create_index("ix_configuration_items_tenant_id", "configuration_items", ["tenant_id"])
    op.create_index(
        "ix_configuration_items_tenant_kind_active",
        "configuration_items",
        ["tenant_id", "kind", "is_active"],
    )
    op.create_table(
        "workflow_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_workflow_definitions_tenant_key"),
    )
    op.create_index("ix_workflow_definitions_tenant_id", "workflow_definitions", ["tenant_id"])
    op.create_table(
        "workflow_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", workflow_status, nullable=False),
        sa.Column("stages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_workflow_version"),
    )
    op.create_index("ix_workflow_versions_tenant_id", "workflow_versions", ["tenant_id"])
    op.create_index(
        "ix_workflow_versions_tenant_status", "workflow_versions", ["tenant_id", "status"]
    )
    for table in ("configuration_items", "workflow_definitions", "workflow_versions"):
        _rls(table)
    op.get_bind().exec_driver_sql("""
        WITH workflows AS (
            INSERT INTO workflow_definitions (id, tenant_id, key, name, description, is_active)
            SELECT gen_random_uuid(), id, 'idea_approval', 'Idea Approval', 'Default approval contract for submitted ideas.', true FROM tenants
            ON CONFLICT (tenant_id, key) DO NOTHING
            RETURNING id, tenant_id
        )
        INSERT INTO workflow_versions (id, tenant_id, workflow_id, version, status, stages, published_at)
        SELECT gen_random_uuid(), tenant_id, id, 1, 'published', '[{"key":"demo_approval","name":"Demo Approval","approver_role":"tenant_admin","sla_hours":48,"required":true}]'::jsonb, now()
        FROM workflows
    """)


def downgrade() -> None:
    op.drop_table("workflow_versions")
    op.drop_table("workflow_definitions")
    op.drop_table("configuration_items")
    workflow_status.drop(op.get_bind(), checkfirst=True)
