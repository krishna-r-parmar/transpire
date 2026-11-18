"""Benefits tracked per month in delivery, validated by Finance.

Moves the month-on-month tracker out of the charter into its own table. Existing tracker rows on
charters that already have a project are copied across. Their months were stored as labels
("Apr" .. "Mar"), so they're placed in the financial year (April to March) the charter was submitted in.

Revision ID: 20261118_0030
Revises: 20261118_0029
Create Date: 2026-11-18
"""

import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261118_0030"
down_revision: str | None = "20261118_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]


def _set_tenant(connection: sa.Connection, tenant_id: object) -> None:
    connection.execute(
        sa.text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def _amount(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _month_date(label: str, anchor: date) -> date | None:
    if label not in _MONTHS:
        return None
    fy_start = anchor.year if anchor.month >= 4 else anchor.year - 1
    index = _MONTHS.index(label)
    month = 4 + index if index < 9 else index - 8
    return date(fy_start if index < 9 else fy_start + 1, month, 1)


def upgrade() -> None:
    op.create_table(
        "project_benefit_months",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("plan", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("actual", sa.Numeric(14, 2), nullable=True),
        sa.Column("line_of_sight", sa.Numeric(14, 2), nullable=True),
        sa.Column("kpi_actual", sa.Numeric(18, 4), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("finance_status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("finance_comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "month", name="uq_project_benefit_month"),
        sa.CheckConstraint(
            "finance_status IN ('open', 'submitted', 'validated', 'challenged')",
            name="ck_project_benefit_months_finance_status",
        ),
    )
    op.create_index("ix_project_benefit_months_tenant_id", "project_benefit_months", ["tenant_id"])
    op.create_index(
        "ix_project_benefit_months_tenant_project",
        "project_benefit_months",
        ["tenant_id", "project_id", "month"],
    )
    op.execute("ALTER TABLE project_benefit_months ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_benefit_months FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY project_benefit_months_tenant_isolation ON project_benefit_months
        USING (tenant_id = app_current_tenant_id())
        WITH CHECK (tenant_id = app_current_tenant_id())
        """
    )

    connection = op.get_bind()
    tenant_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM tenants"))]
    for tenant_id in tenant_ids:
        _set_tenant(connection, tenant_id)
        rows = connection.execute(
            sa.text(
                """
                SELECT projects.id, charter.monthly_tracking,
                       COALESCE(charter.submitted_at, charter.created_at)
                FROM projects
                JOIN project_charters AS charter ON charter.idea_id = projects.idea_id
                WHERE projects.tenant_id = :tenant_id
                  AND jsonb_array_length(charter.monthly_tracking) > 0
                """
            ),
            {"tenant_id": str(tenant_id)},
        ).all()
        for project_id, tracking, anchor in rows:
            entries = tracking if isinstance(tracking, list) else json.loads(tracking or "[]")
            for entry in entries:
                month = _month_date(str(entry.get("month") or ""), anchor.date())
                plan, actual = _amount(entry.get("ftm_plan")), _amount(entry.get("ftm_actual"))
                los, kpi = _amount(entry.get("line_of_sight")), _amount(entry.get("kpi_actual"))
                if month is None or not any(value for value in (plan, actual, los, kpi)):
                    continue
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO project_benefit_months (
                            id, tenant_id, project_id, month, plan, actual, line_of_sight,
                            kpi_actual, status, finance_status
                        ) VALUES (
                            gen_random_uuid(), :tenant_id, :project_id, :month, :plan, :actual,
                            :los, :kpi, :status, :finance_status
                        )
                        ON CONFLICT (project_id, month) DO NOTHING
                        """
                    ),
                    {
                        "tenant_id": str(tenant_id),
                        "project_id": str(project_id),
                        "month": month,
                        "plan": plan or 0,
                        "actual": actual,
                        "los": los,
                        "kpi": kpi,
                        "status": str(entry.get("status") or "")[:16],
                        "finance_status": "validated" if entry.get("finance_approved") else "open",
                    },
                )


def downgrade() -> None:
    op.drop_table("project_benefit_months")
