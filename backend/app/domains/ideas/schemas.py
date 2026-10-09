import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

IdeaType = Literal["kaizen", "project"]
ImpactType = Literal["safety", "quality", "delivery", "cost", "productivity"]
DetailLevel = Literal["headline", "operational", "full"]
ApprovalDecision = Literal["approve", "needs_correction", "reject"]
BenefitType = Literal["cost_saving", "cost_avoidance", "both", "revenue", "kpi_only"]
ActionStatus = Literal["pending", "in_progress", "complete"]
TrackingStatus = Literal["", "on_track", "delayed", "achieved"]


class IdeaUpsertCommand(BaseModel):
    draft_step: int = Field(default=1, ge=1, le=4)
    idea_type: IdeaType = "kaizen"
    project_category: str | None = Field(default=None, max_length=80)
    project_subtype: str | None = Field(default=None, max_length=80)
    site_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    process_area_id: uuid.UUID | None = None
    title: str = Field(default="", max_length=120)
    problem_statement: str = Field(default="", max_length=600)
    business_case: str = Field(default="", max_length=600)
    current_state: str = Field(default="", max_length=500)
    baseline_uom: str = Field(default="", max_length=40)
    target_state: str = Field(default="", max_length=500)
    target_uom: str = Field(default="", max_length=40)
    target_completion_date: date | None = None
    impacts: list[ImpactType] = Field(default_factory=list, max_length=5)
    estimated_annual_saving: Decimal | None = Field(default=None, ge=0)
    cost_avoidance: Decimal | None = Field(default=None, ge=0)
    investment_required: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def project_fields_match_type(self) -> "IdeaUpsertCommand":
        if self.idea_type == "kaizen":
            self.project_category = None
            self.project_subtype = None
        return self


class IdeaRecord(BaseModel):
    id: uuid.UUID
    reference: str
    status: str
    idea_type: str
    title: str
    category_id: uuid.UUID | None
    subcategory_id: uuid.UUID | None
    process_area_id: uuid.UUID | None
    impacts: list[str]
    updated_at: datetime
    submitted_at: datetime | None
    draft_step: int


class EditableIdeaRecord(IdeaUpsertCommand):
    id: uuid.UUID
    reference: str
    status: Literal["draft", "needs_correction"]
    updated_at: datetime
    correction_reason: str | None = None


class IdeaBankEntry(BaseModel):
    id: uuid.UUID
    reference: str
    title: str
    status: str
    idea_type: str
    category: str | None
    submitted_at: datetime | None
    contributor: str | None = None
    subcategory: str | None = None
    process_area: str | None = None
    impacts: list[str] | None = None
    current_state: str | None = None
    baseline_uom: str | None = None
    target_state: str | None = None
    target_uom: str | None = None
    problem_statement: str | None = None
    business_case: str | None = None
    estimated_annual_saving: Decimal | None = None
    cost_avoidance: Decimal | None = None
    investment_required: Decimal | None = None
    estimated_annual_saving_usd: Decimal | None = None
    cost_avoidance_usd: Decimal | None = None
    investment_required_usd: Decimal | None = None
    usd_exchange_rate: Decimal | None = None
    fx_rate_date: date | None = None


class ExchangeRateRecord(BaseModel):
    base_currency: Literal["INR"] = "INR"
    quote_currency: Literal["USD"] = "USD"
    rate: Decimal
    rate_date: date
    source: str = "Frankfurter"


class IdeaBankPolicyCommand(BaseModel):
    detail_level: DetailLevel
    show_contributor: bool
    show_financials: bool


class IdeaBankPolicySummary(IdeaBankPolicyCommand):
    pass


class CatalogItem(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    parent_id: uuid.UUID | None
    site_ids: list[uuid.UUID] = Field(default_factory=list)
    applies_to_all_sites: bool = False
    guidance: dict[str, object] = Field(default_factory=dict)


class ApprovalStagePreview(BaseModel):
    key: str
    name: str
    approver_role: str
    assignee_name: str | None = None
    assignee_email: str | None = None
    assignee_status: Literal["active", "pending"] | None = None
    sla_hours: int
    required: bool


class ApprovalContractPreview(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    version: int
    stages: list[ApprovalStagePreview]


class IdeaSubmissionCatalog(BaseModel):
    sites: list[CatalogItem]
    departments: list[CatalogItem]
    categories: list[CatalogItem]
    subcategories: list[CatalogItem]
    process_areas: list[CatalogItem]
    approval_contract: ApprovalContractPreview | None = None


class ApprovalStageRecord(BaseModel):
    id: uuid.UUID
    round_number: int
    stage_order: int
    stage_key: str
    stage_name: str
    assignee_name: str
    assignee_email: str
    sla_hours: int
    status: str
    decision_comment: str | None
    due_at: datetime | None
    actioned_at: datetime | None
    is_actionable: bool = False


class CharterActionItem(BaseModel):
    action: str = Field(default="", max_length=500)
    plan_start: date | None = None
    plan_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    owner: str = Field(default="", max_length=200)
    status: ActionStatus = "pending"
    phase: int | None = Field(default=None, ge=0, le=4)


class CharterMonthlyEntry(BaseModel):
    month: str = Field(min_length=3, max_length=3)
    ftm_plan: Decimal | None = Field(default=None, ge=0)
    ftm_actual: Decimal | None = Field(default=None, ge=0)
    line_of_sight: Decimal | None = Field(default=None, ge=0)
    kpi_actual: Decimal | None = None
    status: TrackingStatus = ""


class CharterMonthlyRecord(CharterMonthlyEntry):
    finance_approved: bool = False


class ProjectCharterCommand(BaseModel):
    sponsor: str = Field(default="", max_length=200)
    leader: str = Field(default="", max_length=200)
    department_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
    team_members: list[str] = Field(default_factory=list, max_length=50)
    team_membership_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    in_scope: str = Field(default="", max_length=2000)
    out_of_scope: str = Field(default="", max_length=2000)
    objective: str = Field(default="", max_length=1200)
    benefit_type: BenefitType = "cost_saving"
    kpi_name: str = Field(default="", max_length=160)
    budget_approved: Decimal | None = Field(default=None, ge=0)
    impact_areas: list[ImpactType] = Field(default_factory=list, max_length=5)
    belt_level: str | None = Field(default=None, max_length=40)
    action_items: list[CharterActionItem] = Field(default_factory=list, max_length=200)
    monthly_tracking: list[CharterMonthlyEntry] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "ProjectCharterCommand":
        if (
            self.start_date
            and self.target_completion_date
            and self.target_completion_date < self.start_date
        ):
            raise ValueError("Target completion must be on or after the start date.")
        self.team_members = [name.strip() for name in self.team_members if name.strip()]
        return self


class ProjectCharterRecord(ProjectCharterCommand):
    monthly_tracking: list[CharterMonthlyRecord] = Field(default_factory=list, max_length=12)
    id: uuid.UUID
    status: Literal["draft", "submitted"]
    updated_at: datetime
    submitted_at: datetime | None
    team_invitations_queued: int = 0
    team_invitations_skipped: int = 0


class IdeaDetailRecord(BaseModel):
    id: uuid.UUID
    reference: str
    status: str
    idea_type: str
    project_category: str | None
    project_subtype: str | None
    title: str
    submitter_name: str
    submitter_email: str
    submitted_at: datetime | None
    updated_at: datetime
    site_id: uuid.UUID | None
    site: str | None
    department_id: uuid.UUID | None
    department: str | None
    category: str | None
    subcategory: str | None
    process_area: str | None
    problem_statement: str
    business_case: str
    current_state: str
    baseline_uom: str
    target_state: str
    target_uom: str
    impacts: list[str]
    estimated_annual_saving: Decimal | None
    cost_avoidance: Decimal | None
    investment_required: Decimal | None
    estimated_annual_saving_usd: Decimal | None
    cost_avoidance_usd: Decimal | None
    investment_required_usd: Decimal | None
    usd_exchange_rate: Decimal | None
    fx_rate_date: date | None
    approval_stages: list[ApprovalStageRecord]
    charter_available: bool
    charter: ProjectCharterRecord | None
    can_edit_charter: bool
    can_edit_idea: bool
    correction_reason: str | None


class ApprovalDecisionCommand(BaseModel):
    decision: ApprovalDecision
    comment: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def reason_is_present(self) -> "ApprovalDecisionCommand":
        if self.decision != "approve" and not self.comment.strip():
            raise ValueError("Add a reason before returning or rejecting the idea.")
        return self


class HomeIdeaSummary(BaseModel):
    id: uuid.UUID
    reference: str
    title: str
    idea_type: str
    status: str
    submitted_at: datetime | None
    updated_at: datetime
    current_stage: str | None
    charter_available: bool
    charter_status: str | None
    can_edit_idea: bool
    can_delete_draft: bool
    correction_reason: str | None


class ApprovalWorkItem(BaseModel):
    idea_id: uuid.UUID
    reference: str
    title: str
    idea_type: str
    stage_id: uuid.UUID
    stage_name: str
    submitted_by: str
    submitted_at: datetime | None
    due_at: datetime | None


class HomeWorkspaceSummary(BaseModel):
    ideas: list[HomeIdeaSummary]
    approval_items: list[ApprovalWorkItem]
