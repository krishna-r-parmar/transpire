"""Add URS starter catalogue, idea submission, and Idea Bank policy.

Revision ID: 20260818_0010
Revises: 20260818_0009
Create Date: 2026-08-18
"""

import json
import re
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.domains.configuration.urs_templates import URS_TEMPLATE_CATALOG

revision: str = "20260818_0010"
down_revision: str | None = "20260818_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

idea_status = postgresql.ENUM(
    "draft", "submitted", "withdrawn", name="idea_status", create_type=False
)


def _code(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


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


def _seed_catalogue() -> None:
    connection = op.get_bind()
    tenant_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM tenants"))]
    for tenant_id in tenant_ids:
        for category_index, category in enumerate(URS_TEMPLATE_CATALOG["categories"]):
            assert isinstance(category, dict)
            category_code = _code(str(category["name"]))
            existing = connection.execute(
                sa.text(
                    "SELECT id FROM configuration_items WHERE tenant_id = :tenant_id AND kind = 'category' AND code = :code"
                ),
                {"tenant_id": tenant_id, "code": category_code},
            ).scalar_one_or_none()
            category_id = existing or uuid.uuid4()
            if existing is None:
                connection.execute(
                    sa.text(
                        "INSERT INTO configuration_items (id, tenant_id, kind, code, name, is_active, sort_order, metadata) VALUES (:id, :tenant_id, 'category', :code, :name, true, :sort_order, CAST(:metadata AS jsonb))"
                    ),
                    {
                        "id": category_id,
                        "tenant_id": tenant_id,
                        "code": category_code,
                        "name": str(category["name"]),
                        "sort_order": category_index,
                        "metadata": '{"applies":"Both","source":"URS"}',
                    },
                )
            for subcategory_index, subcategory in enumerate(category["subs"]):
                assert isinstance(subcategory, dict)
                subcategory_code = f"{category_code}_{_code(str(subcategory['name']))}"
                connection.execute(
                    sa.text(
                        "INSERT INTO configuration_items (id, tenant_id, kind, code, name, parent_id, is_active, sort_order, metadata) VALUES (:id, :tenant_id, 'subcategory', :code, :name, :parent_id, true, :sort_order, CAST(:metadata AS jsonb)) ON CONFLICT (tenant_id, kind, code) DO NOTHING"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": tenant_id,
                        "code": subcategory_code,
                        "name": str(subcategory["name"]),
                        "parent_id": category_id,
                        "sort_order": subcategory_index,
                        "metadata": json.dumps(
                            {
                                "title_template": subcategory["titleTemplate"],
                                "problem": subcategory["problem"],
                                "business_case": subcategory["solution"],
                                "kpi": subcategory["kpi"],
                                "area": subcategory["area"],
                                "source": "URS",
                            }
                        ),
                    },
                )
        for area_index, area in enumerate(URS_TEMPLATE_CATALOG["processAreas"]):
            connection.execute(
                sa.text(
                    "INSERT INTO configuration_items (id, tenant_id, kind, code, name, is_active, sort_order, metadata) VALUES (:id, :tenant_id, 'process_area', :code, :name, true, :sort_order, '{\"source\":\"URS\"}'::jsonb) ON CONFLICT (tenant_id, kind, code) DO NOTHING"
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "code": _code(str(area)),
                    "name": str(area),
                    "sort_order": area_index,
                },
            )


def upgrade() -> None:
    op.add_column(
        "configuration_items",
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    idea_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "idea_bank_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("detail_level", sa.String(24), nullable=False, server_default="operational"),
        sa.Column("show_contributor", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_financials", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_idea_bank_policies_tenant"),
    )
    op.create_index("ix_idea_bank_policies_tenant_id", "idea_bank_policies", ["tenant_id"])
    op.create_table(
        "ideas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("submitter_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", idea_status, nullable=False),
        sa.Column("idea_type", sa.String(30), nullable=False, server_default="kaizen"),
        sa.Column("project_category", sa.String(80), nullable=True),
        sa.Column("project_subtype", sa.String(80), nullable=True),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subcategory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("process_area_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(120), nullable=False, server_default=""),
        sa.Column("problem_statement", sa.Text(), nullable=False, server_default=""),
        sa.Column("business_case", sa.Text(), nullable=False, server_default=""),
        sa.Column("current_state", sa.String(500), nullable=False, server_default=""),
        sa.Column("target_state", sa.String(500), nullable=False, server_default=""),
        sa.Column("target_completion_date", sa.Date(), nullable=True),
        sa.Column("impacts", postgresql.ARRAY(sa.String(24)), nullable=False, server_default="{}"),
        sa.Column("estimated_annual_saving", sa.Numeric(16, 2), nullable=True),
        sa.Column("cost_avoidance", sa.Numeric(16, 2), nullable=True),
        sa.Column("investment_required", sa.Numeric(16, 2), nullable=True),
        sa.Column("workflow_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitter_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["configuration_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["department_id"], ["configuration_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["configuration_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["subcategory_id"], ["configuration_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["process_area_id"], ["configuration_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_version_id"], ["workflow_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_ideas_tenant_reference"),
    )
    op.create_index("ix_ideas_tenant_id", "ideas", ["tenant_id"])
    op.create_index(
        "ix_ideas_tenant_status_submitted", "ideas", ["tenant_id", "status", "submitted_at"]
    )
    op.create_index("ix_ideas_tenant_submitter", "ideas", ["tenant_id", "submitter_user_id"])
    for table in ("idea_bank_policies", "ideas"):
        _rls(table)
    op.execute(
        "INSERT INTO idea_bank_policies (id, tenant_id, detail_level, show_contributor, show_financials) SELECT gen_random_uuid(), id, 'operational', true, false FROM tenants ON CONFLICT (tenant_id) DO NOTHING"
    )
    _seed_catalogue()


def downgrade() -> None:
    op.drop_table("ideas")
    op.drop_table("idea_bank_policies")
    idea_status.drop(op.get_bind(), checkfirst=True)
    op.drop_column("configuration_items", "metadata")
