from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.tenant_resolution import ResolvedTenant, get_resolved_tenant
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


def require_tenant_admin(identity: AuthenticatedIdentity) -> SessionIdentity:
    if "tenant_admin" not in identity.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant administrator access is required.",
        )
    return identity


PlatformAdminIdentity = Annotated[SessionIdentity, Depends(require_platform_admin)]
TenantAdminIdentity = Annotated[SessionIdentity, Depends(require_tenant_admin)]


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
    if identity.session_scope != "sso_recovery" or "tenant_admin" not in identity.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a restricted SSO recovery session.",
        )
    return identity


SSORecoveryIdentity = Annotated[SessionIdentity, Depends(get_sso_recovery_identity)]
