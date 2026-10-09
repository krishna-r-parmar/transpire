import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.tenants.models import TenantStatus


class TenantSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    status: TenantStatus


class TenantCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=2, max_length=200)


class TenantProvisionCommand(TenantCreate):
    first_admin_email: EmailStr
    first_admin_name: str = Field(min_length=2, max_length=200)


class TenantProvisionResult(TenantSummary):
    invitation_sent_to: EmailStr


class TenantStatusCommand(BaseModel):
    status: Literal["pending", "active", "suspended"]


class InvitationCreateCommand(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=200)
    role_key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")


class InvitationResult(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    role_key: str
    expires_at: datetime
    message: str = "Invitation queued securely."


class InvitationSummary(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    role_key: str
    status: Literal["pending", "expired", "revoked"]
    expires_at: datetime
    last_sent_at: datetime


class PlatformTenantSummary(TenantSummary):
    created_at: datetime
    invitation: InvitationSummary | None = None


class MembershipStatusCommand(BaseModel):
    status: Literal["active", "inactive"]


class TenantRoleSummary(BaseModel):
    key: str
    name: str


class TenantMemberSummary(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    status: str
    roles: list[str]
