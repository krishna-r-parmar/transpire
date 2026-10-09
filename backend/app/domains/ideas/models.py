import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class IdeaStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    NEEDS_CORRECTION = "needs_correction"
    REJECTED = "rejected"
    APPROVED = "approved"
    CHARTER_IN_PROGRESS = "charter_in_progress"
    CHARTER_SUBMITTED = "charter_submitted"
    WITHDRAWN = "withdrawn"


class Idea(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "ideas"
    __table_args__ = (
        UniqueConstraint("tenant_id", "reference", name="uq_ideas_tenant_reference"),
        CheckConstraint("draft_step >= 1 AND draft_step <= 4", name="ck_ideas_draft_step_range"),
        Index("ix_ideas_tenant_status_submitted", "tenant_id", "status", "submitted_at"),
        Index("ix_ideas_tenant_submitter", "tenant_id", "submitter_user_id"),
    )

    reference: Mapped[str] = mapped_column(String(40), nullable=False)
    submitter_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[IdeaStatus] = mapped_column(
        Enum(
            IdeaStatus,
            name="idea_status",
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=IdeaStatus.DRAFT,
    )
    draft_step: Mapped[int] = mapped_column(nullable=False, default=1)
    idea_type: Mapped[str] = mapped_column(String(30), nullable=False, default="kaizen")
    project_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    project_subtype: Mapped[str | None] = mapped_column(String(80), nullable=True)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="RESTRICT"), nullable=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="RESTRICT"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="RESTRICT"), nullable=True
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="RESTRICT"), nullable=True
    )
    process_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="RESTRICT"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    business_case: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_state: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    baseline_uom: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    target_state: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    target_uom: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    impacts: Mapped[list[str]] = mapped_column(ARRAY(String(24)), nullable=False, default=list)
    estimated_annual_saving: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    cost_avoidance: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    investment_required: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    usd_exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="RESTRICT"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdeaBankPolicy(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "idea_bank_policies"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_idea_bank_policies_tenant"),)

    detail_level: Mapped[str] = mapped_column(String(24), nullable=False, default="operational")
    show_contributor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_financials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class IdeaApprovalStage(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "idea_approval_stages"
    __table_args__ = (
        UniqueConstraint(
            "idea_id", "round_number", "stage_order", name="uq_idea_approval_stage_round_order"
        ),
        Index("ix_idea_approval_stages_tenant_assignee", "tenant_id", "assignee_user_id", "status"),
        Index("ix_idea_approval_stages_tenant_idea", "tenant_id", "idea_id"),
    )

    idea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(nullable=False, default=1)
    stage_order: Mapped[int] = mapped_column(nullable=False)
    stage_key: Mapped[str] = mapped_column(String(80), nullable=False)
    stage_name: Mapped[str] = mapped_column(String(160), nullable=False)
    assignee_membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False
    )
    assignee_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assignee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    assignee_email: Mapped[str] = mapped_column(String(320), nullable=False)
    sla_hours: Mapped[int] = mapped_column(nullable=False, default=48)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="waiting")
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectCharter(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "project_charters"
    __table_args__ = (
        UniqueConstraint("idea_id", name="uq_project_charters_idea"),
        Index("ix_project_charters_tenant_idea", "tenant_id", "idea_id"),
    )

    idea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False
    )
    sponsor: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    leader: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="RESTRICT"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="RESTRICT"), nullable=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    team_members: Mapped[list[str]] = mapped_column(
        ARRAY(String(200)), nullable=False, default=list
    )
    team_membership_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    in_scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    out_of_scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    benefit_type: Mapped[str] = mapped_column(String(40), nullable=False, default="cost_saving")
    kpi_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    budget_approved: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    impact_areas: Mapped[list[str]] = mapped_column(ARRAY(String(24)), nullable=False, default=list)
    belt_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action_items: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    monthly_tracking: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
