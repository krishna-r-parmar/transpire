import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError

from app.domains.configuration.controllers import (
    ConfigurationConflictError,
    ConfigurationNotFoundError,
    create_item,
    create_workflow_version,
    list_items,
    list_workflow_assignees,
    list_workflows,
    publish_workflow_version,
    update_item,
)
from app.domains.configuration.schemas import (
    ConfigurationItemCreate,
    ConfigurationItemSummary,
    ConfigurationItemUpdate,
    ConfigurationKind,
    WorkflowAssigneeSummary,
    WorkflowSummary,
    WorkflowVersionCreate,
    WorkflowVersionSummary,
)
from app.domains.identity.dependencies import (
    SessionDependency,
    TenantAdminIdentity,
    TenantDependency,
)

router = APIRouter(prefix="/admin/configuration", tags=["tenant configuration"])


@router.get("/master-data/{kind}", response_model=list[ConfigurationItemSummary])
async def get_configuration_items(
    kind: ConfigurationKind,
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> list[ConfigurationItemSummary]:
    return await list_items(tenant.tenant_id, kind, session)


@router.post(
    "/master-data/{kind}",
    response_model=ConfigurationItemSummary,
    status_code=status.HTTP_201_CREATED,
)
async def post_configuration_item(
    kind: ConfigurationKind,
    command: ConfigurationItemCreate,
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ConfigurationItemSummary:
    try:
        return await create_item(tenant.tenant_id, kind, command, session)
    except ConfigurationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except IntegrityError as error:
        raise HTTPException(
            status_code=409, detail="That code is already in use for this configuration type."
        ) from error


@router.patch("/master-data/{kind}/{item_id}", response_model=ConfigurationItemSummary)
async def patch_configuration_item(
    kind: ConfigurationKind,
    item_id: uuid.UUID,
    command: ConfigurationItemUpdate,
    _: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ConfigurationItemSummary:
    try:
        return await update_item(tenant.tenant_id, kind, item_id, command, session)
    except ConfigurationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Configuration item not found.") from error
    except ConfigurationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/workflows/contracts", response_model=list[WorkflowSummary])
async def get_workflow_contracts(
    _: TenantAdminIdentity, tenant: TenantDependency, session: SessionDependency
) -> list[WorkflowSummary]:
    return await list_workflows(tenant.tenant_id, session)


@router.get("/workflows/assignees", response_model=list[WorkflowAssigneeSummary])
async def get_workflow_assignees(
    _: TenantAdminIdentity, tenant: TenantDependency, session: SessionDependency
) -> list[WorkflowAssigneeSummary]:
    return await list_workflow_assignees(tenant.tenant_id, session)


@router.post(
    "/workflows/{workflow_id}/versions", response_model=WorkflowVersionSummary, status_code=201
)
async def post_workflow_version(
    workflow_id: uuid.UUID,
    command: WorkflowVersionCreate,
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> WorkflowVersionSummary:
    try:
        return await create_workflow_version(
            tenant.tenant_id, identity.user.id, workflow_id, command, session
        )
    except ConfigurationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Workflow not found.") from error
    except ConfigurationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/workflows/{workflow_id}/versions/{version_id}/publish", status_code=204)
async def publish_workflow(
    workflow_id: uuid.UUID,
    version_id: uuid.UUID,
    identity: TenantAdminIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> Response:
    try:
        await publish_workflow_version(
            tenant.tenant_id, identity.user.id, workflow_id, version_id, session
        )
    except ConfigurationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Workflow version not found.") from error
    except ConfigurationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(status_code=204)
