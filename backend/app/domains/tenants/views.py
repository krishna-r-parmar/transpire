import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.tenant_resolution import ResolvedTenant
from app.domains.identity.dependencies import (
    PlatformAdminIdentity,
    SessionDependency,
    SettingsDependency,
    TenantAdminIdentity,
    TenantDependency,
)
from app.domains.identity.models import MembershipStatus
from app.domains.identity.schemas import SSORecoveryCommand, SSORecoveryResult
from app.domains.identity.sso import SSOConfigurationError, issue_recovery
from app.domains.tenants.controllers import (
    InvitationConflictError,
    InvitationNotFoundError,
    MembershipConflictError,
    RoleNotFoundError,
    TenantConflictError,
    change_membership_status,
    change_tenant_status,
    invite_member,
    list_invitations,
    list_members,
    list_platform_tenants,
    list_roles,
    provision_tenant,
    remove_tenant,
    resend_invitation,
    revoke_invitation,
)
from app.domains.tenants.models import TenantStatus
from app.domains.tenants.schemas import (
    InvitationCreateCommand,
    InvitationResult,
    InvitationSummary,
    MembershipStatusCommand,
    PlatformTenantSummary,
    TenantMemberSummary,
    TenantProvisionCommand,
    TenantProvisionResult,
    TenantRoleSummary,
    TenantStatusCommand,
)

router = APIRouter(tags=["tenant administration"])


@router.post(
    "/platform/tenants/{tenant_id}/sso/recovery",
    response_model=SSORecoveryResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_sso_recovery(
    tenant_id: uuid.UUID,
    command: SSORecoveryCommand,
    identity: PlatformAdminIdentity,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SSORecoveryResult:
    async with session.begin():
        row = (
            await session.execute(
                text("SELECT * FROM resolve_tenant_by_id(:tenant_id)"),
                {"tenant_id": tenant_id},
            )
        ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    target = ResolvedTenant(
        tenant_id=row["tenant_id"], slug=row["slug"], name=row["name"], status=row["status"]
    )
    try:
        return await issue_recovery(command, identity, target, settings, session)
    except SSOConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/platform/tenants", response_model=list[PlatformTenantSummary])
async def get_platform_tenants(
    _: PlatformAdminIdentity,
    session: SessionDependency,
) -> list[PlatformTenantSummary]:
    return await list_platform_tenants(session)


@router.post(
    "/platform/tenants",
    response_model=TenantProvisionResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_platform_tenant(
    command: TenantProvisionCommand,
    identity: PlatformAdminIdentity,
    settings: SettingsDependency,
    session: SessionDependency,
) -> TenantProvisionResult:
    try:
        return await provision_tenant(command, identity, settings, session)
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) != "23505":
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That tenant shortname is already in use.",
        ) from error
    except InvitationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.patch("/platform/tenants/{tenant_id}/status", status_code=status.HTTP_204_NO_CONTENT)
async def update_platform_tenant_status(
    tenant_id: uuid.UUID,
    command: TenantStatusCommand,
    identity: PlatformAdminIdentity,
    session: SessionDependency,
) -> Response:
    try:
        await change_tenant_status(
            tenant_id, TenantStatus(command.status), identity.tenant.id, session
        )
    except TenantConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/platform/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_platform_tenant(
    tenant_id: uuid.UUID,
    identity: PlatformAdminIdentity,
    session: SessionDependency,
) -> Response:
    try:
        await remove_tenant(tenant_id, identity.tenant.id, session)
    except TenantConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/platform/tenants/{tenant_id}/invitations/{invitation_id}/resend",
    response_model=InvitationResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend_platform_tenant_invitation(
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
    identity: PlatformAdminIdentity,
    settings: SettingsDependency,
    session: SessionDependency,
) -> InvitationResult:
    try:
        return await resend_invitation(tenant_id, invitation_id, identity, settings, session)
    except InvitationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found."
        ) from error
    except (InvitationConflictError, TenantConflictError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.delete(
    "/platform/tenants/{tenant_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_platform_tenant_invitation(
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
    _: PlatformAdminIdentity,
    session: SessionDependency,
) -> Response:
    try:
        await revoke_invitation(tenant_id, invitation_id, session)
    except InvitationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found."
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/platform/tenants/{tenant_id}/members",
    response_model=list[TenantMemberSummary],
)
async def get_platform_tenant_members(
    tenant_id: uuid.UUID,
    _: PlatformAdminIdentity,
    session: SessionDependency,
) -> list[TenantMemberSummary]:
    return await list_members(tenant_id, session)


@router.patch(
    "/platform/tenants/{tenant_id}/members/{membership_id}/status",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_platform_tenant_member_status(
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    command: MembershipStatusCommand,
    identity: PlatformAdminIdentity,
    session: SessionDependency,
) -> Response:
    try:
        await change_membership_status(
            tenant_id,
            membership_id,
            MembershipStatus(command.status),
            identity,
            session,
        )
    except MembershipConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/members", response_model=list[TenantMemberSummary])
async def get_tenant_members(
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> list[TenantMemberSummary]:
    return await list_members(tenant.tenant_id, session)


@router.get("/admin/roles", response_model=list[TenantRoleSummary])
async def get_tenant_roles(
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> list[TenantRoleSummary]:
    return await list_roles(tenant.tenant_id, session)


@router.get("/admin/invitations", response_model=list[InvitationSummary])
async def get_tenant_invitations(
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> list[InvitationSummary]:
    return await list_invitations(tenant.tenant_id, session)


@router.post(
    "/admin/invitations",
    response_model=InvitationResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_tenant_invitation(
    command: InvitationCreateCommand,
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> InvitationResult:
    try:
        return await invite_member(
            command,
            tenant.tenant_id,
            tenant.name,
            identity,
            settings,
            session,
        )
    except RoleNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The selected role is unavailable.",
        ) from error
    except InvitationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post(
    "/admin/invitations/{invitation_id}/resend",
    response_model=InvitationResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend_tenant_invitation(
    invitation_id: uuid.UUID,
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> InvitationResult:
    try:
        return await resend_invitation(tenant.tenant_id, invitation_id, identity, settings, session)
    except InvitationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found."
        ) from error
    except (InvitationConflictError, TenantConflictError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.delete("/admin/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_tenant_invitation(
    invitation_id: uuid.UUID,
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> Response:
    try:
        await revoke_invitation(tenant.tenant_id, invitation_id, session)
    except InvitationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found."
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/admin/members/{membership_id}/status", status_code=status.HTTP_204_NO_CONTENT)
async def update_tenant_member_status(
    membership_id: uuid.UUID,
    command: MembershipStatusCommand,
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> Response:
    try:
        await change_membership_status(
            tenant.tenant_id,
            membership_id,
            MembershipStatus(command.status),
            identity,
            session,
        )
    except MembershipConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
