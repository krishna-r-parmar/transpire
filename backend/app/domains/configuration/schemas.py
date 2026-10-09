import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

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


class WorkflowStage(BaseModel):
    key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    name: str = Field(min_length=2, max_length=160)
    approver_role: str = Field(default="tenant_admin", pattern=r"^[a-z0-9_]+$")
    assignee_membership_id: uuid.UUID | None = None
    assignee_name: str | None = None
    assignee_email: EmailStr | None = None
    assignee_status: Literal["active", "pending"] | None = None
    sla_hours: int = Field(default=48, ge=1, le=8760)
    required: bool = True


class WorkflowStageCreate(BaseModel):
    key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    name: str = Field(min_length=2, max_length=160)
    assignee_membership_id: uuid.UUID
    sla_hours: int = Field(default=48, ge=1, le=8760)
    required: bool = True


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
