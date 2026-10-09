from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.tenant_resolution import ResolvedTenant, get_resolved_tenant
from app.domains.identity.controllers import (
    AuthenticationThrottledError,
    ClientContext,
    InvalidCredentialsError,
    InvalidInvitationTokenError,
    InvalidPasswordResetTokenError,
    InvalidSessionError,
    InvalidWorkspaceSelectionError,
    InvitationPasswordRequiredError,
    IssuedSession,
    accept_invitation,
    central_sign_in,
    inspect_invitation,
    list_user_workspaces,
    read_session,
    request_global_password_reset,
    reset_password,
    select_workspace,
    sign_out,
)
from app.domains.identity.dependencies import AuthenticatedIdentity
from app.domains.identity.schemas import (
    CentralSignInResult,
    InvitationAcceptanceCommand,
    InvitationAcceptanceResult,
    InvitationInspectionResult,
    InvitationTokenCommand,
    PasswordResetCommand,
    PasswordResetRequestCommand,
    PasswordResetRequestResult,
    PasswordResetResult,
    SessionIdentity,
    SignInCommand,
    WorkspaceChoice,
    WorkspaceSelectionCommand,
)
from app.domains.identity.sso import tenant_requires_sso

router = APIRouter(prefix="/auth", tags=["authentication"])

TenantDependency = Annotated[ResolvedTenant, Depends(get_resolved_tenant)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def _client_context(request: Request) -> ClientContext:
    return ClientContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] or None,
    )


def _session_cookie(request: Request, settings: Settings) -> str | None:
    return request.cookies.get(settings.session_cookie_name)


def _set_session_cookies(
    response: Response,
    issued: IssuedSession,
    settings: Settings,
) -> None:
    max_age = (
        settings.remembered_session_days * 24 * 60 * 60
        if issued.persistent
        else None
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=issued.token,
        max_age=max_age,
        expires=issued.identity.expires_at if issued.persistent else None,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=issued.csrf_token,
        max_age=max_age,
        expires=issued.identity.expires_at if issued.persistent else None,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )


@router.post("/sign-in", response_model=CentralSignInResult)
async def create_session(
    command: SignInCommand,
    request: Request,
    response: Response,
    settings: SettingsDependency,
    session: SessionDependency,
) -> CentralSignInResult:
    route_tenant = getattr(request.state, "tenant", None)
    if isinstance(route_tenant, ResolvedTenant) and await tenant_requires_sso(
        session, route_tenant.tenant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This organisation requires Microsoft SSO.",
        )
    if command.preferred_tenant_slug is None and isinstance(route_tenant, ResolvedTenant):
        command = command.model_copy(
            update={"preferred_tenant_slug": route_tenant.slug}
        )
    try:
        outcome = await central_sign_in(
            command,
            _client_context(request),
            settings,
            session,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        ) from error
    except AuthenticationThrottledError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Try again later.",
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error

    if outcome.issued_session is not None:
        _set_session_cookies(response, outcome.issued_session, settings)
    return outcome.result


@router.post("/select-workspace", response_model=CentralSignInResult)
async def choose_workspace(
    command: WorkspaceSelectionCommand,
    request: Request,
    response: Response,
    settings: SettingsDependency,
    session: SessionDependency,
) -> CentralSignInResult:
    try:
        outcome = await select_workspace(
            command,
            _client_context(request),
            settings,
            session,
        )
    except InvalidWorkspaceSelectionError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This workspace selection has expired. Sign in again.",
        ) from error
    if outcome.issued_session is not None:
        _set_session_cookies(response, outcome.issued_session, settings)
    return outcome.result


@router.get("/session", response_model=SessionIdentity)
async def get_current_session(
    request: Request,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SessionIdentity:
    try:
        return await read_session(_session_cookie(request, settings), tenant, session)
    except InvalidSessionError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        ) from error


@router.get("/workspaces", response_model=list[WorkspaceChoice])
async def get_user_workspaces(
    identity: AuthenticatedIdentity,
    session: SessionDependency,
) -> list[WorkspaceChoice]:
    return await list_user_workspaces(identity.user.id, session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    request: Request,
    response: Response,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> None:
    await sign_out(
        _session_cookie(request, settings),
        tenant,
        _client_context(request),
        session,
    )
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )


@router.post(
    "/password-reset/request",
    response_model=PasswordResetRequestResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_password_reset_request(
    command: PasswordResetRequestCommand,
    request: Request,
    settings: SettingsDependency,
    session: SessionDependency,
) -> PasswordResetRequestResult:
    route_tenant = getattr(request.state, "tenant", None)
    if isinstance(route_tenant, ResolvedTenant) and await tenant_requires_sso(
        session, route_tenant.tenant_id
    ):
        return PasswordResetRequestResult()
    await request_global_password_reset(
        command,
        _client_context(request),
        settings,
        session,
    )
    return PasswordResetRequestResult()


@router.post("/password-reset/complete", response_model=PasswordResetResult)
async def complete_password_reset(
    command: PasswordResetCommand,
    request: Request,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> PasswordResetResult:
    if await tenant_requires_sso(session, tenant.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Password recovery is unavailable because this organisation requires Microsoft SSO.",
        )
    try:
        await reset_password(
            command,
            tenant,
            _client_context(request),
            settings,
            session,
        )
    except InvalidPasswordResetTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired.",
        ) from error
    return PasswordResetResult()


@router.post("/invitations/inspect", response_model=InvitationInspectionResult)
async def get_invitation_details(
    command: InvitationTokenCommand,
    settings: SettingsDependency,
    session: SessionDependency,
) -> InvitationInspectionResult:
    try:
        return await inspect_invitation(command, settings, session)
    except InvalidInvitationTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation is invalid or has expired.",
        ) from error


@router.post("/invitations/accept", response_model=InvitationAcceptanceResult)
async def complete_invitation(
    command: InvitationAcceptanceCommand,
    request: Request,
    settings: SettingsDependency,
    session: SessionDependency,
) -> InvitationAcceptanceResult:
    try:
        await accept_invitation(
            command,
            _client_context(request),
            settings,
            session,
        )
    except InvalidInvitationTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation is invalid or has expired.",
        ) from error
    except InvitationPasswordRequiredError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Create a password to accept this invitation.",
        ) from error
    except AuthenticationThrottledError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many invitation attempts. Try again later.",
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error
    return InvitationAcceptanceResult()
