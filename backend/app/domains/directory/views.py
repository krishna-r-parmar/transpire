from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.domains.directory.controllers import (
    get_overview,
    list_runs,
    search_employees,
    update_settings,
)
from app.domains.directory.parser import MAX_FILE_BYTES
from app.domains.directory.schemas import (
    DirectoryEmployeeSummary,
    DirectoryOverview,
    DirectoryRunSummary,
    DirectorySettings,
    SftpActionResult,
    SftpSourceCommand,
    SftpSourceView,
    TrustHostKeyCommand,
)
from app.domains.directory.sftp_controllers import (
    SftpNotConfiguredError,
    check_server_key,
    fetch_and_apply,
    get_sftp_source,
    save_sftp_source,
    test_sftp_source,
    trust_server_key,
)
from app.domains.directory.sync import process_inbox, run_directory_sync
from app.domains.identity.dependencies import (
    SessionDependency,
    SettingsDependency,
    TenantAdminIdentity,
    TenantDependency,
    WorkspaceOwnerIdentity,
)

router = APIRouter(prefix="/admin/directory", tags=["hr directory"])


@router.get("", response_model=DirectoryOverview)
async def get_directory_overview(
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> DirectoryOverview:
    return await get_overview(tenant.tenant_id, tenant.slug, settings, session)


@router.put("/settings", response_model=DirectorySettings)
async def put_directory_settings(
    command: DirectorySettings,
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> DirectorySettings:
    return await update_settings(tenant.tenant_id, identity.user.id, command, session)


@router.get("/runs", response_model=list[DirectoryRunSummary])
async def get_directory_runs(
    _: TenantAdminIdentity, tenant: TenantDependency, session: SessionDependency
) -> list[DirectoryRunSummary]:
    return await list_runs(tenant.tenant_id, session)


@router.get("/employees", response_model=list[DirectoryEmployeeSummary])
async def get_directory_employees(
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
    query: Annotated[str, Query(max_length=120)] = "",
) -> list[DirectoryEmployeeSummary]:
    return await search_employees(tenant.tenant_id, query, session)


@router.post("/upload", response_model=DirectoryRunSummary)
async def upload_directory_file(
    request: Request,
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
    file_name: Annotated[str, Query(min_length=5, max_length=200)],
    mode: Annotated[str, Query(pattern="^(preview|apply)$")] = "preview",
    force: bool = False,
) -> DirectoryRunSummary:
    """Upload the HR report as the raw request body (preview first, then apply)."""
    content = await request.body()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB.")
    return await run_directory_sync(
        tenant_id=tenant.tenant_id,
        content=content,
        file_name=file_name,
        source="upload",
        actor=identity,
        settings=settings,
        session=session,
        apply=mode == "apply",
        force=force,
    )


@router.post("/inbox/process", response_model=list[DirectoryRunSummary])
async def process_directory_inbox(
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> list[DirectoryRunSummary]:
    return await process_inbox(
        tenant_id=tenant.tenant_id,
        tenant_slug=tenant.slug,
        actor=identity,
        settings=settings,
        session=session,
    )


NOT_CONFIGURED = "Save the SFTP server address first."


@router.get("/sftp", response_model=SftpSourceView)
async def get_directory_sftp(
    _: TenantAdminIdentity, tenant: TenantDependency, session: SessionDependency
) -> SftpSourceView:
    return await get_sftp_source(tenant.tenant_id, session)


@router.put("/sftp", response_model=SftpSourceView)
async def put_directory_sftp(
    command: SftpSourceCommand,
    identity: WorkspaceOwnerIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SftpSourceView:
    return await save_sftp_source(tenant.tenant_id, identity, command, settings, session)


@router.post("/sftp/check-key", response_model=SftpActionResult)
async def post_directory_sftp_check_key(
    _: WorkspaceOwnerIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SftpActionResult:
    try:
        return await check_server_key(tenant.tenant_id, settings, session)
    except SftpNotConfiguredError as error:
        raise HTTPException(status_code=409, detail=NOT_CONFIGURED) from error


@router.post("/sftp/trust-key", response_model=SftpSourceView)
async def post_directory_sftp_trust_key(
    command: TrustHostKeyCommand,
    identity: WorkspaceOwnerIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> SftpSourceView:
    try:
        return await trust_server_key(tenant.tenant_id, identity, command.fingerprint, session)
    except SftpNotConfiguredError as error:
        raise HTTPException(
            status_code=409,
            detail="That fingerprint is not the one the server presented. Check the server again.",
        ) from error


@router.post("/sftp/test", response_model=SftpActionResult)
async def post_directory_sftp_test(
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SftpActionResult:
    try:
        return await test_sftp_source(tenant.tenant_id, settings, session)
    except SftpNotConfiguredError as error:
        raise HTTPException(status_code=409, detail=NOT_CONFIGURED) from error


@router.post("/sftp/fetch", response_model=SftpActionResult)
async def post_directory_sftp_fetch(
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> SftpActionResult:
    """Ad-hoc run: fetch the newest report now and apply it."""
    try:
        return await fetch_and_apply(
            tenant_id=tenant.tenant_id,
            tenant_slug=tenant.slug,
            actor=identity,
            settings=settings,
            session=session,
        )
    except SftpNotConfiguredError as error:
        raise HTTPException(status_code=409, detail=NOT_CONFIGURED) from error
