from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.tenant_resolution import ResolvedTenant, get_resolved_tenant
from app.domains.identity.controllers import ClientContext, IssuedSession
from app.domains.identity.dependencies import SSORecoveryIdentity, TenantAdminIdentity
from app.domains.identity.schemas import (
    SignInResult,
    SSOActivationResult,
    SSOConfigurationCommand,
    SSOConfigurationResult,
    SSORecoveryConfigurationCommand,
    SSORecoveryRedeemCommand,
    SSOWorkspaceSelectionCommand,
    WorkspaceChoice,
)
from app.domains.identity.sso import (
    SSOAuthenticationError,
    SSOConfigurationError,
    activate_sso,
    begin_global_sso,
    begin_sso,
    complete_global_sso,
    complete_sso,
    configure_sso,
    get_sso_configuration,
    list_sso_workspace_choices,
    redeem_recovery,
    repair_sso_configuration,
    select_sso_workspace,
)

router = APIRouter(tags=["Microsoft SSO"])
TenantDependency = Annotated[ResolvedTenant, Depends(get_resolved_tenant)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def _client(request: Request) -> ClientContext:
    return ClientContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] or None,
    )


def _set_session(response: Response, issued: IssuedSession, settings: Settings) -> None:
    max_age = settings.remembered_session_days * 86400 if issued.persistent else None
    response.set_cookie(
        settings.session_cookie_name,
        issued.token,
        max_age=max_age,
        expires=issued.identity.expires_at if issued.persistent else None,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        issued.csrf_token,
        max_age=max_age,
        expires=issued.identity.expires_at if issued.persistent else None,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )


@router.get("/auth/sso/global/start")
async def start_global_sso_sign_in(
    settings: SettingsDependency,
    session: SessionDependency,
    remember_me: bool = Query(default=False),
) -> RedirectResponse:
    try:
        target = await begin_global_sso(settings, session, remember_me=remember_me)
    except SSOConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/auth/sso/global/callback")
async def global_sso_callback(
    request: Request,
    settings: SettingsDependency,
    session: SessionDependency,
    code: str = Query(min_length=1),
    state_token: str = Query(alias="state", min_length=32),
) -> RedirectResponse:
    try:
        outcome = await complete_global_sso(
            code=code,
            raw_state=state_token,
            client=_client(request),
            settings=settings,
            session=session,
        )
    except (SSOAuthenticationError, httpx.HTTPError):
        return RedirectResponse(
            f"{settings.public_app_url.rstrip('/')}/sign-in?sso_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    response = RedirectResponse(outcome.redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    if outcome.issued_session:
        _set_session(response, outcome.issued_session, settings)
    if outcome.selection_token:
        response.set_cookie(
            settings.sso_selection_cookie_name,
            outcome.selection_token,
            max_age=settings.workspace_selection_minutes * 60,
            path="/api/v1/auth/sso/global",
            secure=settings.session_cookie_secure,
            httponly=True,
            samesite="lax",
        )
    return response


@router.get("/auth/sso/global/workspaces", response_model=list[WorkspaceChoice])
async def get_global_sso_workspaces(
    request: Request,
    settings: SettingsDependency,
    session: SessionDependency,
) -> list[WorkspaceChoice]:
    try:
        return await list_sso_workspace_choices(
            request.cookies.get(settings.sso_selection_cookie_name), session
        )
    except SSOAuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error


@router.post("/auth/sso/global/select-workspace", response_model=SignInResult)
async def choose_global_sso_workspace(
    command: SSOWorkspaceSelectionCommand,
    request: Request,
    response: Response,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SignInResult:
    try:
        issued = await select_sso_workspace(
            raw_token=request.cookies.get(settings.sso_selection_cookie_name),
            tenant_id=command.tenant_id,
            client=_client(request),
            settings=settings,
            session=session,
        )
    except SSOAuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    _set_session(response, issued, settings)
    response.delete_cookie(
        settings.sso_selection_cookie_name,
        path="/api/v1/auth/sso/global",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return issued.identity


@router.get("/auth/sso/status")
async def sso_status(
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> dict[str, bool]:
    result = await get_sso_configuration(tenant.tenant_id, settings, session)
    return {"enabled": result.status == "active"}


@router.get("/auth/sso/start")
async def start_sso_sign_in(
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
    remember_me: bool = Query(default=False),
) -> RedirectResponse:
    try:
        target = await begin_sso(
            tenant, settings, session, purpose="sign_in", remember_me=remember_me
        )
    except SSOConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/auth/sso/callback")
async def sso_callback(
    request: Request,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
    code: str = Query(min_length=1),
    state_token: str = Query(alias="state", min_length=32),
) -> RedirectResponse:
    try:
        outcome = await complete_sso(
            code=code,
            raw_state=state_token,
            tenant=tenant,
            client=_client(request),
            settings=settings,
            session=session,
        )
    except (SSOAuthenticationError, httpx.HTTPError):
        return RedirectResponse(
            f"{settings.public_app_url.rstrip('/')}/t/{tenant.slug}/sign-in?sso_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    response = RedirectResponse(outcome.redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    if outcome.issued_session:
        _set_session(response, outcome.issued_session, settings)
    return response


@router.get("/admin/sso", response_model=SSOConfigurationResult)
async def read_sso_configuration(
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SSOConfigurationResult:
    return await get_sso_configuration(tenant.tenant_id, settings, session)


@router.put("/admin/sso", response_model=SSOConfigurationResult)
async def update_sso_configuration(
    command: SSOConfigurationCommand,
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SSOConfigurationResult:
    try:
        return await configure_sso(command, identity, tenant.tenant_id, settings, session)
    except SSOConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/admin/sso/validate")
async def validate_sso_configuration(
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> RedirectResponse:
    try:
        target = await begin_sso(
            tenant,
            settings,
            session,
            purpose="validate",
            initiated_by_user_id=identity.user.id,
        )
    except SSOConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/sso/activate", response_model=SSOActivationResult)
async def activate_sso_configuration(
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SSOActivationResult:
    try:
        return await activate_sso(identity, tenant, settings, session)
    except SSOConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/auth/sso/recovery/redeem", status_code=status.HTTP_204_NO_CONTENT)
async def redeem_sso_recovery(
    command: SSORecoveryRedeemCommand,
    request: Request,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> Response:
    try:
        issued = await redeem_recovery(
            command.token, tenant, _client(request), settings, session
        )
    except SSOAuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _set_session(response, issued, settings)
    return response


@router.put("/admin/sso/recovery", status_code=status.HTTP_204_NO_CONTENT)
async def repair_sso(
    command: SSORecoveryConfigurationCommand,
    identity: SSORecoveryIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> Response:
    await repair_sso_configuration(command.entra_directory_id, tenant.tenant_id, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
