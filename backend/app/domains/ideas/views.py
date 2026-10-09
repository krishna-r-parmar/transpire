import uuid

from fastapi import APIRouter, HTTPException, status

from app.domains.ideas.controllers import (
    IdeaAccessError,
    IdeaNotFoundError,
    IdeaValidationError,
    decide_approval_stage,
    delete_draft_idea,
    get_catalog,
    get_editable_idea,
    get_home_workspace,
    get_idea_bank_policy,
    get_idea_detail,
    list_idea_bank,
    resubmit_idea,
    save_idea,
    save_project_charter,
    submit_idea,
    update_idea_bank_policy,
)
from app.domains.ideas.fx import ExchangeRateUnavailableError, get_inr_usd_rate
from app.domains.ideas.schemas import (
    ApprovalDecisionCommand,
    EditableIdeaRecord,
    ExchangeRateRecord,
    HomeWorkspaceSummary,
    IdeaBankEntry,
    IdeaBankPolicyCommand,
    IdeaBankPolicySummary,
    IdeaDetailRecord,
    IdeaRecord,
    IdeaSubmissionCatalog,
    IdeaUpsertCommand,
    ProjectCharterCommand,
    ProjectCharterRecord,
)
from app.domains.identity.dependencies import (
    AuthenticatedIdentity,
    SessionDependency,
    SettingsDependency,
    TenantAdminIdentity,
    TenantDependency,
)

router = APIRouter(prefix="/ideas", tags=["ideas"])
admin_router = APIRouter(prefix="/admin/configuration", tags=["tenant configuration"])


@router.get("", response_model=list[IdeaBankEntry])
async def get_ideas(
    _: AuthenticatedIdentity, tenant: TenantDependency, session: SessionDependency
) -> list[IdeaBankEntry]:
    return await list_idea_bank(tenant.tenant_id, session)


@router.get("/submission-catalog", response_model=IdeaSubmissionCatalog)
async def get_idea_submission_catalog(
    _: AuthenticatedIdentity, tenant: TenantDependency, session: SessionDependency
) -> IdeaSubmissionCatalog:
    return await get_catalog(tenant.tenant_id, session)


@router.get("/home-summary", response_model=HomeWorkspaceSummary)
async def read_home_workspace(
    identity: AuthenticatedIdentity, tenant: TenantDependency, session: SessionDependency
) -> HomeWorkspaceSummary:
    return await get_home_workspace(tenant.tenant_id, identity.user.id, session)


@router.get("/exchange-rate", response_model=ExchangeRateRecord)
async def read_exchange_rate(
    _: AuthenticatedIdentity, settings: SettingsDependency
) -> ExchangeRateRecord:
    try:
        return await get_inr_usd_rate(settings)
    except ExchangeRateUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail="USD conversion is temporarily unavailable. INR values can still be saved.",
        ) from error


@router.get("/{idea_id}/edit", response_model=EditableIdeaRecord)
async def read_editable_idea(
    idea_id: uuid.UUID,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> EditableIdeaRecord:
    try:
        return await get_editable_idea(tenant.tenant_id, identity.user.id, idea_id, session)
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Editable idea not found.") from error


@router.get("/{idea_id}", response_model=IdeaDetailRecord)
async def read_idea_detail(
    idea_id: uuid.UUID,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> IdeaDetailRecord:
    try:
        return await get_idea_detail(
            tenant.tenant_id, identity.user.id, identity.roles, idea_id, session
        )
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Idea not found.") from error
    except IdeaAccessError as error:
        raise HTTPException(
            status_code=403, detail="You do not have access to this idea."
        ) from error


@router.post("/{idea_id}/approvals/{stage_id}", response_model=IdeaDetailRecord)
async def decide_approval(
    idea_id: uuid.UUID,
    stage_id: uuid.UUID,
    command: ApprovalDecisionCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> IdeaDetailRecord:
    try:
        return await decide_approval_stage(
            tenant.tenant_id,
            identity.user.id,
            idea_id,
            stage_id,
            command,
            settings,
            session,
        )
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Approval item not found.") from error
    except IdeaAccessError as error:
        raise HTTPException(
            status_code=403, detail="This approval item is assigned to another person."
        ) from error
    except IdeaValidationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/{idea_id}/charter", response_model=ProjectCharterRecord)
async def save_charter(
    idea_id: uuid.UUID,
    command: ProjectCharterCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> ProjectCharterRecord:
    try:
        return await save_project_charter(
            tenant.tenant_id, identity.user.id, idea_id, command, settings, session
        )
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Idea not found.") from error
    except IdeaAccessError as error:
        raise HTTPException(
            status_code=403, detail="Only the idea owner can edit this charter."
        ) from error
    except IdeaValidationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{idea_id}/charter/submit", response_model=ProjectCharterRecord)
async def submit_charter(
    idea_id: uuid.UUID,
    command: ProjectCharterCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> ProjectCharterRecord:
    try:
        return await save_project_charter(
            tenant.tenant_id,
            identity.user.id,
            idea_id,
            command,
            settings,
            session,
            submit=True,
        )
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Idea not found.") from error
    except IdeaAccessError as error:
        raise HTTPException(
            status_code=403, detail="Only the idea owner can submit this charter."
        ) from error
    except IdeaValidationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("", response_model=IdeaRecord, status_code=status.HTTP_201_CREATED)
async def create_idea(
    command: IdeaUpsertCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> IdeaRecord:
    try:
        return await save_idea(tenant.tenant_id, identity.user.id, command, session)
    except IdeaValidationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/{idea_id}", response_model=IdeaRecord)
async def update_idea(
    idea_id: uuid.UUID,
    command: IdeaUpsertCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> IdeaRecord:
    try:
        return await save_idea(tenant.tenant_id, identity.user.id, command, session, idea_id)
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Editable idea not found.") from error
    except IdeaValidationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{idea_id}/submit", response_model=IdeaRecord)
async def submit_draft(
    idea_id: uuid.UUID,
    command: IdeaUpsertCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> IdeaRecord:
    try:
        return await submit_idea(
            tenant.tenant_id, identity.user.id, idea_id, command, session, settings
        )
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Draft idea not found.") from error
    except IdeaValidationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{idea_id}/resubmit", response_model=IdeaRecord)
async def resubmit_corrected_idea(
    idea_id: uuid.UUID,
    command: IdeaUpsertCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> IdeaRecord:
    try:
        return await resubmit_idea(
            tenant.tenant_id, identity.user.id, idea_id, command, session, settings
        )
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Corrected idea not found.") from error
    except IdeaValidationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    idea_id: uuid.UUID,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> None:
    try:
        await delete_draft_idea(tenant.tenant_id, identity.user.id, idea_id, session)
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Draft idea not found.") from error


@admin_router.get("/idea-bank-policy", response_model=IdeaBankPolicySummary)
async def read_idea_bank_policy(
    _: TenantAdminIdentity, tenant: TenantDependency, session: SessionDependency
) -> IdeaBankPolicySummary:
    return await get_idea_bank_policy(tenant.tenant_id, session)


@admin_router.put("/idea-bank-policy", response_model=IdeaBankPolicySummary)
async def write_idea_bank_policy(
    command: IdeaBankPolicyCommand,
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> IdeaBankPolicySummary:
    return await update_idea_bank_policy(tenant.tenant_id, command, session)
