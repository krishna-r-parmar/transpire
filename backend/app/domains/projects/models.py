import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
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


class ProjectStatus(str, enum.Enum):
    # Opened when the idea is fully approved; becomes ready_to_start once the charter is submitted.
    CHARTER_IN_PROGRESS = "charter_in_progress"
    READY_TO_START = "ready_to_start"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    COMPLETION_REVIEW = "completion_review"
    OE_VERIFIED = "oe_verified"
    FINANCE_VALIDATION = "finance_validation"
    SUCCESS = "success"
    CANCELLED = "cancelled"
    UNSUCCESSFUL = "unsuccessful"


class ProjectHealth(str, enum.Enum):
    NOT_SET = "not_set"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BLOCKED = "blocked"


class Project(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("idea_id", name="uq_projects_idea"),
        UniqueConstraint("tenant_id", "reference", name="uq_projects_tenant_reference"),
        Index("ix_projects_tenant_status", "tenant_id", "status", "target_completion_date"),
    )

    idea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ideas.id", ondelete="RESTRICT"), nullable=False
    )
    reference: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProjectStatus.READY_TO_START.value
    )
    health: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ProjectHealth.NOT_SET.value
    )
    active_baseline_version: Mapped[int] = mapped_column(nullable=False, default=1)
    lead_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    oe_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finance_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectCharterBaseline(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "project_charter_baselines"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_project_charter_baseline_version"),
        Index("ix_project_charter_baselines_tenant_project", "tenant_id", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="Initial submitted charter")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectMilestone(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "project_milestones"
    __table_args__ = (
        UniqueConstraint("project_id", "position", name="uq_project_milestone_position"),
        CheckConstraint("weight >= 0 AND weight <= 100", name="ck_project_milestone_weight"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_project_milestone_progress"),
        Index("ix_project_milestones_tenant_project", "tenant_id", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    progress: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_started")
    completion_criteria: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dependency_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    # What the submitted charter promised. Re-planning changes planned_end/weight and records why;
    # these stay as the baseline so the variance is always visible.
    baseline_planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    benefits_start: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ProjectAction(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "project_actions"
    __table_args__ = (
        Index("ix_project_actions_tenant_milestone", "tenant_id", "milestone_id", "status"),
    )

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_milestones.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_started")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class ProjectTeamMember(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "project_team_members"
    __table_args__ = (
        UniqueConstraint("project_id", "membership_id", name="uq_project_team_membership"),
        Index("ix_project_team_members_tenant_project", "tenant_id", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    email_snapshot: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="invited")
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectBenefitMonth(UUIDPrimaryKeyMixin, TenantOwnedMixin, TimestampMixin, Base):
    """One month of realised benefit, recorded in delivery and validated by Finance.

    Months open when the milestone marked "benefits start" is complete. Amounts are in ₹ lakhs.
    """

    __tablename__ = "project_benefit_months"
    __table_args__ = (
        UniqueConstraint("project_id", "month", name="uq_project_benefit_month"),
        Index("ix_project_benefit_months_tenant_project", "tenant_id", "project_id", "month"),
        CheckConstraint(
            "finance_status IN ('open', 'submitted', 'validated', 'challenged')",
            name="ck_project_benefit_months_finance_status",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    plan: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    actual: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    line_of_sight: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    kpi_actual: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    finance_status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    finance_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
