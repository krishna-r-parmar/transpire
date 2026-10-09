import uuid

from fastapi import APIRouter, HTTPException

from app.domains.identity.dependencies import (
    AuthenticatedIdentity,
    SessionDependency,
    TenantDependency,
)
from app.domains.projects.controllers import (
    ProjectAccessError,
    ProjectNotFoundError,
    get_project_workspace,
    list_projects,
    list_team_candidates,
    save_milestone_plan,
)
from app.domains.projects.schemas import (
    ProjectMilestonePlanCommand,
    ProjectPortfolioEntry,
    ProjectTeamCandidate,
    ProjectWorkspaceRecord,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/team-candidates", response_model=list[ProjectTeamCandidate])
async def get_project_team_candidates(
    _: AuthenticatedIdentity, tenant: TenantDependency, session: SessionDependency
) -> list[ProjectTeamCandidate]:
    return await list_team_candidates(tenant.tenant_id, session)


@router.get("", response_model=list[ProjectPortfolioEntry])
async def get_projects(
    _: AuthenticatedIdentity, tenant: TenantDependency, session: SessionDependency
) -> list[ProjectPortfolioEntry]:
    return await list_projects(tenant.tenant_id, session)


@router.get("/{project_id}", response_model=ProjectWorkspaceRecord)
async def get_project(
    project_id: uuid.UUID,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    try:
        return await get_project_workspace(
            tenant.tenant_id, identity.user.id, identity.roles, project_id, session
        )
    except ProjectNotFoundError as error:
        raise HTTPException(status_code=404, detail="Project not found.") from error


@router.put("/{project_id}/milestones", response_model=ProjectWorkspaceRecord)
async def put_milestone_plan(
    project_id: uuid.UUID,
    command: ProjectMilestonePlanCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    try:
        return await save_milestone_plan(
            tenant.tenant_id,
            identity.user.id,
            identity.roles,
            project_id,
            command,
            session,
        )
    except ProjectNotFoundError as error:
        raise HTTPException(status_code=404, detail="Project not found.") from error
    except ProjectAccessError as error:
        raise HTTPException(status_code=403, detail="You cannot manage this milestone plan.") from error
