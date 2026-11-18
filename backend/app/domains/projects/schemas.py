import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ProjectPortfolioEntry(BaseModel):
    id: uuid.UUID
    idea_id: uuid.UUID
    reference: str
    idea_reference: str
    title: str
    status: str
    health: str
    lead_name: str
    site: str | None
    department: str | None
    target_completion_date: date | None
    baseline_version: int
    milestone_count: int
    progress: Decimal
    target: Decimal
    achieved: Decimal
    validated: Decimal
    line_of_sight: Decimal
    projected_outcome: Decimal
    updated_at: datetime


class ProjectTeamCandidate(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    email: str


class ProjectActionRecord(BaseModel):
    id: uuid.UUID
    title: str
    owner_name: str
    owner_user_id: uuid.UUID | None
    due_date: date | None
    completed_at: datetime | None
    status: str
    notes: str


class ProjectActionCommand(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str = Field(min_length=1, max_length=500)
    owner_name: str = Field(default="", max_length=200)
    owner_user_id: uuid.UUID | None = None
    due_date: date | None = None
    status: str = Field(
        default="not_started", pattern="^(not_started|in_progress|blocked|complete)$"
    )
    notes: str = Field(default="", max_length=2000)


class ProjectMilestoneRecord(BaseModel):
    id: uuid.UUID
    position: int
    title: str
    outcome: str
    owner_name: str
    owner_user_id: uuid.UUID | None
    planned_start: date | None
    planned_end: date | None
    actual_start: date | None
    actual_end: date | None
    weight: Decimal
    progress: Decimal
    status: str
    completion_criteria: str
    evidence: str
    dependency_ids: list[uuid.UUID]
    actions: list[ProjectActionRecord]
    baseline_planned_end: date | None = None
    baseline_weight: Decimal | None = None
    benefits_start: bool = False
    # Days the current due date sits after (+) or before (-) the charter baseline.
    variance_days: int | None = None


class ProjectMilestoneCommand(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    position: int = Field(ge=1, le=100)
    title: str = Field(min_length=1, max_length=200)
    outcome: str = Field(default="", max_length=2000)
    owner_name: str = Field(default="", max_length=200)
    owner_user_id: uuid.UUID | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    weight: Decimal = Field(ge=0, le=100)
    progress: Decimal = Field(ge=0, le=100)
    status: str = Field(
        default="not_started", pattern="^(not_started|in_progress|blocked|complete)$"
    )
    completion_criteria: str = Field(default="", max_length=2000)
    evidence: str = Field(default="", max_length=4000)
    dependency_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    actions: list[ProjectActionCommand] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "ProjectMilestoneCommand":
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("Milestone end date must be on or after its start date.")
        return self


class ProjectMilestonePlanCommand(BaseModel):
    milestones: list[ProjectMilestoneCommand] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def plan_is_consistent(self) -> "ProjectMilestonePlanCommand":
        ids = [milestone.id for milestone in self.milestones]
        positions = [milestone.position for milestone in self.milestones]
        if len(ids) != len(set(ids)) or len(positions) != len(set(positions)):
            raise ValueError("Milestone identifiers and positions must be unique.")
        if sum((milestone.weight for milestone in self.milestones), Decimal(0)) > 100:
            raise ValueError("Milestone weights cannot total more than 100%.")
        known = set(ids)
        for milestone in self.milestones:
            dependencies = set(milestone.dependency_ids)
            if milestone.id in dependencies or not dependencies.issubset(known):
                raise ValueError(
                    "Milestone dependencies must reference another milestone in this project."
                )
        return self


MilestoneStatus = Literal["not_started", "in_progress", "blocked", "complete"]


class MilestonePatchCommand(BaseModel):
    """Change one milestone. Only the fields sent are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    outcome: str | None = Field(default=None, max_length=2000)
    owner_user_id: uuid.UUID | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    weight: Decimal | None = Field(default=None, ge=0, le=100)
    progress: Decimal | None = Field(default=None, ge=0, le=100)
    status: MilestoneStatus | None = None
    completion_criteria: str | None = Field(default=None, max_length=2000)
    evidence: str | None = Field(default=None, max_length=4000)
    benefits_start: bool | None = None
    # Required when the change moves the charter baseline (due date, weight, or title).
    reason: str = Field(default="", max_length=500)


class MilestoneCreateCommand(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    owner_user_id: uuid.UUID | None = None
    planned_end: date | None = None
    weight: Decimal = Field(default=Decimal(0), ge=0, le=100)
    reason: str = Field(default="", max_length=500)


class MilestoneMoveCommand(BaseModel):
    direction: Literal["up", "down"]


class TaskCreateCommand(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    owner_user_id: uuid.UUID | None = None
    due_date: date | None = None


class TaskPatchCommand(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    owner_user_id: uuid.UUID | None = None
    due_date: date | None = None
    status: MilestoneStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ProjectTeamMemberRecord(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    status: str
    invited_at: datetime
    responded_at: datetime | None


class ProjectBaselineRecord(BaseModel):
    id: uuid.UUID
    version: int
    reason: str
    created_by_name: str
    published_at: datetime
    is_active: bool


class ProjectActivityRecord(BaseModel):
    id: uuid.UUID
    event_type: str
    summary: str
    actor_name: str | None
    created_at: datetime


class ProjectCharterSnapshotRecord(BaseModel):
    sponsor: str = ""
    leader: str = ""
    start_date: date | None = None
    target_completion_date: date | None = None
    team_members: list[str] = Field(default_factory=list)
    in_scope: str = ""
    out_of_scope: str = ""
    objective: str = ""
    benefit_type: str = ""
    kpi_name: str = ""
    budget_approved: Decimal | None = None
    impact_areas: list[str] = Field(default_factory=list)
    belt_level: str | None = None
    action_items: list[dict[str, object]] = Field(default_factory=list)


class ProjectBenefitPeriodRecord(BaseModel):
    month: str  # YYYY-MM
    plan: Decimal
    achieved: Decimal
    line_of_sight: Decimal
    kpi_actual: Decimal | None
    status: str
    finance_approved: bool
    has_actual: bool = False
    notes: str = ""
    finance_status: str = "open"
    finance_comment: str = ""


class BenefitTrackingRecord(BaseModel):
    """Where benefit tracking stands for a project."""

    # waiting: the benefits-start milestone isn't complete; open: months are being recorded;
    # unplanned: no milestone marks when benefits start yet.
    state: Literal["waiting", "open", "unplanned"]
    milestone_title: str | None = None
    milestone_due: date | None = None
    milestone_status: str | None = None
    annual_target: Decimal  # ₹ lakhs a year, from the approved idea
    kpi_only: bool
    kpi_name: str = ""
    kpi_baseline: str = ""
    kpi_target: str = ""
    can_record: bool
    can_validate: bool


class BenefitMonthCommand(BaseModel):
    plan: Decimal | None = Field(default=None, ge=0, le=Decimal(999999))
    actual: Decimal | None = Field(default=None, ge=Decimal(-999999), le=Decimal(999999))
    line_of_sight: Decimal | None = Field(default=None, ge=0, le=Decimal(999999))
    kpi_actual: Decimal | None = None
    status: Literal["", "on_track", "delayed", "achieved"] | None = None
    notes: str | None = Field(default=None, max_length=1000)


class BenefitReviewCommand(BaseModel):
    decision: Literal["validate", "challenge"]
    comment: str = Field(default="", max_length=1000)


class ProjectWorkspaceRecord(BaseModel):
    id: uuid.UUID
    idea_id: uuid.UUID
    reference: str
    idea_reference: str
    title: str
    idea_type: str
    project_category: str | None
    project_subtype: str | None
    status: str
    health: str
    lead_name: str
    site: str | None
    department: str | None
    start_date: date | None
    target_completion_date: date | None
    baseline_version: int
    progress: Decimal
    target: Decimal
    achieved: Decimal
    validated: Decimal
    line_of_sight: Decimal
    projected_outcome: Decimal
    charter: ProjectCharterSnapshotRecord
    benefit_periods: list[ProjectBenefitPeriodRecord]
    benefits: BenefitTrackingRecord | None = None
    milestones: list[ProjectMilestoneRecord]
    team: list[ProjectTeamMemberRecord]
    baselines: list[ProjectBaselineRecord]
    activity: list[ProjectActivityRecord]
    can_manage_plan: bool
    owner_candidates: list[ProjectTeamCandidate]
    updated_at: datetime
