from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.tenant_resolution import ResolvedTenant, get_resolved_tenant
from app.domains.identity.access import (
    can_contribute,
    is_workspace_admin,
    is_workspace_owner,
)
from app.domains.identity.controllers import InvalidSessionError, read_session
from app.domains.identity.schemas import SessionIdentity

TenantDependency = Annotated[ResolvedTenant, Depends(get_resolved_tenant)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def get_authenticated_identity(
    request: Request,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SessionIdentity:
    try:
        identity = await read_session(
            request.cookies.get(settings.session_cookie_name),
            tenant,
            session,
        )
        if identity.session_scope != "full":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This recovery session is restricted to SSO repair.",
            )
        return identity
    except InvalidSessionError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        ) from error


AuthenticatedIdentity = Annotated[SessionIdentity, Depends(get_authenticated_identity)]


def require_platform_admin(identity: AuthenticatedIdentity) -> SessionIdentity:
    if not identity.user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )
    return identity


def require_contributor(identity: AuthenticatedIdentity) -> SessionIdentity:
    if not can_contribute(identity.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers have read-only access to this workspace.",
        )
    return identity


def require_tenant_admin(identity: AuthenticatedIdentity) -> SessionIdentity:
    if not is_workspace_admin(identity.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace Admin access is required.",
        )
    return identity


def require_workspace_owner(identity: AuthenticatedIdentity) -> SessionIdentity:
    if not is_workspace_owner(identity.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace Owner access is required.",
        )
    return identity


PlatformAdminIdentity = Annotated[SessionIdentity, Depends(require_platform_admin)]
ContributorIdentity = Annotated[SessionIdentity, Depends(require_contributor)]
TenantAdminIdentity = Annotated[SessionIdentity, Depends(require_tenant_admin)]
WorkspaceOwnerIdentity = Annotated[SessionIdentity, Depends(require_workspace_owner)]


async def get_sso_recovery_identity(
    request: Request,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SessionIdentity:
    try:
        identity = await read_session(
            request.cookies.get(settings.session_cookie_name), tenant, session
        )
    except InvalidSessionError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid recovery session is required.",
        ) from error
    if identity.session_scope != "sso_recovery" or not is_workspace_owner(identity.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a restricted SSO recovery session.",
        )
    return identity


SSORecoveryIdentity = Annotated[SessionIdentity, Depends(get_sso_recovery_identity)]
