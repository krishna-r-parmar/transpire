import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

ConfigurationKind = Literal["site", "department", "category", "subcategory", "process_area"]


class ConfigurationItemCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    name: str = Field(min_length=2, max_length=160)
    parent_id: uuid.UUID | None = None
    site_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    applies_to_all_sites: bool = False
    sort_order: int = Field(default=0, ge=0, le=10000)
    guidance: dict[str, str] = Field(default_factory=dict)


class ConfigurationItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    guidance: dict[str, str] | None = None
    site_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    applies_to_all_sites: bool | None = None


class ConfigurationItemSummary(BaseModel):
    id: uuid.UUID
    kind: str
    code: str
    name: str
    parent_id: uuid.UUID | None
    site_ids: list[uuid.UUID] = Field(default_factory=list)
    applies_to_all_sites: bool = False
    is_active: bool
    sort_order: int
    guidance: dict[str, object]


StageSource = Literal["dynamic", "group", "person"]
DynamicRelationship = Literal["reporting_manager", "hod"]
# any: first approver decides. round_robin: one approver, in rotation.
# all_sequential: everyone, one after another. all_parallel: everyone, at the same time.
StageMode = Literal["any", "round_robin", "all_sequential", "all_parallel"]
# skip: move on to the next step. fallback_group: send to another group.
# fallback_admin: send to a Workspace Admin (how pre-builder contracts behaved).
UnresolvedRule = Literal["skip", "fallback_group", "fallback_admin"]
# Who else is emailed the idea and asked for comments when the step starts.
NotifyKind = Literal["none", "group", "hods_same_location", "hods_all"]
GroupPurpose = Literal["approval", "notification"]


class WorkflowStageCreate(BaseModel):
    """One step drawn in the workflow builder."""

    key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    name: str = Field(min_length=2, max_length=160)
    source: StageSource = "group"
    relationship: DynamicRelationship | None = None
    group_id: uuid.UUID | None = None
    assignee_membership_id: uuid.UUID | None = None
    mode: StageMode = "any"
    on_unresolved: UnresolvedRule = "skip"
    fallback_group_id: uuid.UUID | None = None
    skip_if_same_as_previous: bool = True
    notify_kind: NotifyKind = "none"
    notify_group_id: uuid.UUID | None = None
    sla_hours: int = Field(default=48, ge=1, le=8760)
    required: bool = True

    @model_validator(mode="before")
    @classmethod
    def infer_source(cls, data: object) -> object:
        # Pre-builder clients send only an assignee: that is a single-person step.
        if isinstance(data, dict) and not data.get("source") and data.get("assignee_membership_id"):
            return {**data, "source": "person"}
        return data

    @model_validator(mode="after")
    def complete_for_source(self) -> "WorkflowStageCreate":
        if self.source == "dynamic" and self.relationship is None:
            raise ValueError(f"{self.name}: choose Reporting manager or Head of department.")
        if self.source == "group" and self.group_id is None:
            raise ValueError(f"{self.name}: choose an approver group.")
        if self.source == "person" and self.assignee_membership_id is None:
            raise ValueError(f"{self.name}: choose a person.")
        if self.on_unresolved == "fallback_group" and self.fallback_group_id is None:
            raise ValueError(f"{self.name}: choose the fallback group.")
        if self.notify_kind == "group" and self.notify_group_id is None:
            raise ValueError(f"{self.name}: choose the group to notify.")
        return self


class WorkflowStage(WorkflowStageCreate):
    """A stored step, with display names resolved for the admin console."""

    approver_role: str = "assigned_member"
    group_name: str | None = None
    fallback_group_name: str | None = None
    notify_group_name: str | None = None
    assignee_name: str | None = None
    assignee_email: EmailStr | None = None
    assignee_status: Literal["active", "pending"] | None = None

    @model_validator(mode="after")
    def complete_for_source(self) -> "WorkflowStage":
        # Stored history is shown as recorded, even when a group was later removed.
        return self


class WorkflowVersionCreate(BaseModel):
    stages: list[WorkflowStageCreate] = Field(min_length=1, max_length=20)

    @field_validator("stages")
    @classmethod
    def unique_stage_keys(cls, stages: list[WorkflowStageCreate]) -> list[WorkflowStageCreate]:
        if len({stage.key for stage in stages}) != len(stages):
            raise ValueError("Workflow stage keys must be unique.")
        return stages


class WorkflowVersionSummary(BaseModel):
    id: uuid.UUID
    version: int
    status: str
    stages: list[WorkflowStage]
    published_at: datetime | None
    created_at: datetime


class WorkflowSummary(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str
    is_active: bool
    versions: list[WorkflowVersionSummary]


class WorkflowAssigneeSummary(BaseModel):
    membership_id: uuid.UUID
    display_name: str
    email: EmailStr
    status: Literal["active", "pending"]


class ApproverGroupCommand(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    purpose: GroupPurpose = "approval"
    description: str = Field(default="", max_length=500)
    member_membership_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    is_active: bool = True

    @field_validator("member_membership_ids")
    @classmethod
    def unique_members(cls, members: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(members)) != len(members):
            raise ValueError("Each person can be in a group only once.")
        return members


class ApproverGroupMember(BaseModel):
    membership_id: uuid.UUID
    display_name: str
    email: str
    status: Literal["active", "pending", "unavailable"]


class ApproverGroupSummary(BaseModel):
    id: uuid.UUID
    name: str
    purpose: GroupPurpose
    description: str
    is_active: bool
    members: list[ApproverGroupMember]
    used_by_published_workflow: bool = False


class WorkflowPreviewCommand(BaseModel):
    """Dry-run a draft against one employee from the HR directory."""

    stages: list[WorkflowStageCreate] = Field(min_length=1, max_length=20)
    employee_id: str = Field(min_length=1, max_length=64)


class PreviewApprover(BaseModel):
    display_name: str
    email: str | None


class PreviewStep(BaseModel):
    key: str
    name: str
    outcome: Literal["assigned", "skipped"]
    mode: str
    approvers: list[PreviewApprover]
    note: str


class WorkflowPreviewResult(BaseModel):
    employee_name: str
    employee_email: str | None
    steps: list[PreviewStep]
