import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignInCommand(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    remember_me: bool = False
    preferred_tenant_slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=63,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )


class AuthenticatedUser(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    is_platform_admin: bool = False


class AuthenticatedTenant(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class SessionIdentity(BaseModel):
    user: AuthenticatedUser
    tenant: AuthenticatedTenant
    roles: list[str]
    expires_at: datetime
    session_scope: str = "full"


class SignInResult(SessionIdentity):
    authenticated: bool = True
    message: str = "Signed in securely."


class WorkspaceChoice(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class CentralSignInResult(BaseModel):
    selection_required: bool
    selection_token: str | None = None
    workspaces: list[WorkspaceChoice] = Field(default_factory=list)
    session: SignInResult | None = None


class WorkspaceSelectionCommand(BaseModel):
    selection_token: str = Field(min_length=32, max_length=512)
    tenant_id: uuid.UUID


class SSOWorkspaceSelectionCommand(BaseModel):
    tenant_id: uuid.UUID


class PasswordResetRequestCommand(BaseModel):
    email: EmailStr


class PasswordResetRequestResult(BaseModel):
    message: str = (
        "If an active account matches that email, password reset instructions are on their way."
    )


class PasswordResetCommand(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordResetResult(BaseModel):
    message: str = "Your password has been reset. Sign in with your new password."


class InvitationTokenCommand(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class InvitationInspectionResult(BaseModel):
    email: EmailStr
    display_name: str
    tenant_name: str
    sign_in_url: str
    requires_password: bool
    sso_required: bool = False
    expires_at: datetime


class InvitationAcceptanceCommand(InvitationTokenCommand):
    new_password: str | None = Field(default=None, min_length=12, max_length=256)


class InvitationAcceptanceResult(BaseModel):
    message: str = "Your invitation has been accepted. You can now sign in."


class SSOConfigurationCommand(BaseModel):
    entra_directory_id: uuid.UUID


class SSOReadinessMember(BaseModel):
    membership_id: uuid.UUID
    email: EmailStr
    display_name: str
    status: str
    linked: bool
    ready: bool
    reason: str | None = None


class SSOConfigurationResult(BaseModel):
    status: str
    entra_directory_id: str | None = None
    client_id_configured: bool = False
    validated_at: datetime | None = None
    activated_at: datetime | None = None
    active_user_count: int = 0
    ready_user_count: int = 0
    notification_count: int = 0
    members: list[SSOReadinessMember] = Field(default_factory=list)


class SSOActivationResult(SSOConfigurationResult):
    message: str = "Microsoft SSO is now required for this organisation."


class SSORecoveryCommand(BaseModel):
    membership_id: uuid.UUID
    incident_reference: str = Field(min_length=3, max_length=160)


class SSORecoveryResult(BaseModel):
    expires_at: datetime
    message: str = "A restricted, single-use recovery link has been queued."


class SSORecoveryRedeemCommand(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class SSORecoveryConfigurationCommand(BaseModel):
    entra_directory_id: uuid.UUID
