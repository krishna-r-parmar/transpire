import uuid
from collections.abc import Awaitable

from fastapi import APIRouter, HTTPException

from app.domains.ideas.controllers import IdeaNotFoundError, get_charter_workspace
from app.domains.ideas.schemas import CharterWorkspaceRecord
from app.domains.identity.dependencies import (
    AuthenticatedIdentity,
    ContributorIdentity,
    SessionDependency,
    TenantDependency,
)
from app.domains.projects.controllers import (
    ProjectAccessError,
    ProjectNotFoundError,
    ProjectValidationError,
    add_milestone,
    add_task,
    get_project_workspace,
    list_projects,
    list_team_candidates,
    move_milestone,
    record_benefit_month,
    remove_milestone,
    review_benefit_month,
    save_milestone_plan,
    submit_benefit_month,
    update_milestone,
    update_task,
)
from app.domains.projects.schemas import (
    BenefitMonthCommand,
    BenefitReviewCommand,
    MilestoneCreateCommand,
    MilestoneMoveCommand,
    MilestonePatchCommand,
    ProjectMilestonePlanCommand,
    ProjectPortfolioEntry,
    ProjectTeamCandidate,
    ProjectWorkspaceRecord,
    TaskCreateCommand,
    TaskPatchCommand,
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


@router.get("/{project_id}/charter", response_model=CharterWorkspaceRecord)
async def get_project_charter(
    project_id: uuid.UUID,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> CharterWorkspaceRecord:
    try:
        return await get_charter_workspace(tenant.tenant_id, identity.user.id, project_id, session)
    except IdeaNotFoundError as error:
        raise HTTPException(status_code=404, detail="Project not found.") from error


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
    identity: ContributorIdentity,
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
        raise HTTPException(
            status_code=403, detail="You cannot manage this milestone plan."
        ) from error


async def _plan_change(action: Awaitable[ProjectWorkspaceRecord]) -> ProjectWorkspaceRecord:
    """Run one plan change and turn domain errors into clear HTTP responses."""
    try:
        return await action
    except ProjectNotFoundError as error:
        raise HTTPException(status_code=404, detail="Milestone or project not found.") from error
    except ProjectAccessError as error:
        raise HTTPException(
            status_code=403, detail="Only the project lead and team can change this plan."
        ) from error
    except ProjectValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{project_id}/milestones", response_model=ProjectWorkspaceRecord)
async def post_milestone(
    project_id: uuid.UUID,
    command: MilestoneCreateCommand,
    identity: ContributorIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        add_milestone(
            tenant.tenant_id, identity.user.id, identity.roles, project_id, command, session
        )
    )


@router.patch("/{project_id}/milestones/{milestone_id}", response_model=ProjectWorkspaceRecord)
async def patch_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    command: MilestonePatchCommand,
    identity: ContributorIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        update_milestone(
            tenant.tenant_id,
            identity.user.id,
            identity.roles,
            project_id,
            milestone_id,
            command,
            session,
        )
    )


@router.delete("/{project_id}/milestones/{milestone_id}", response_model=ProjectWorkspaceRecord)
async def delete_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    identity: ContributorIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
    reason: str = "",
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        remove_milestone(
            tenant.tenant_id,
            identity.user.id,
            identity.roles,
            project_id,
            milestone_id,
            reason[:500],
            session,
        )
    )


@router.post("/{project_id}/milestones/{milestone_id}/move", response_model=ProjectWorkspaceRecord)
async def post_milestone_move(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    command: MilestoneMoveCommand,
    identity: ContributorIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        move_milestone(
            tenant.tenant_id,
            identity.user.id,
            identity.roles,
            project_id,
            milestone_id,
            command,
            session,
        )
    )


@router.post("/{project_id}/milestones/{milestone_id}/tasks", response_model=ProjectWorkspaceRecord)
async def post_task(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    command: TaskCreateCommand,
    identity: ContributorIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        add_task(
            tenant.tenant_id,
            identity.user.id,
            identity.roles,
            project_id,
            milestone_id,
            command,
            session,
        )
    )


@router.patch(
    "/{project_id}/milestones/{milestone_id}/tasks/{task_id}", response_model=ProjectWorkspaceRecord
)
async def patch_task(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    task_id: uuid.UUID,
    command: TaskPatchCommand,
    identity: ContributorIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        update_task(
            tenant.tenant_id,
            identity.user.id,
            identity.roles,
            project_id,
            milestone_id,
            task_id,
            command,
            session,
        )
    )


@router.delete(
    "/{project_id}/milestones/{milestone_id}/tasks/{task_id}", response_model=ProjectWorkspaceRecord
)
async def delete_task(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    task_id: uuid.UUID,
    identity: ContributorIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        update_task(
            tenant.tenant_id,
            identity.user.id,
            identity.roles,
            project_id,
            milestone_id,
            task_id,
            TaskPatchCommand(),
            session,
            delete_task=True,
        )
    )


@router.patch("/{project_id}/benefits/{month}", response_model=ProjectWorkspaceRecord)
async def patch_benefit_month(
    project_id: uuid.UUID,
    month: str,
    command: BenefitMonthCommand,
    identity: ContributorIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        record_benefit_month(
            tenant.tenant_id, identity.user.id, identity.roles, project_id, month, command, session
        )
    )


@router.post("/{project_id}/benefits/{month}/submit", response_model=ProjectWorkspaceRecord)
async def post_benefit_submit(
    project_id: uuid.UUID,
    month: str,
    identity: ContributorIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        submit_benefit_month(
            tenant.tenant_id, identity.user.id, identity.roles, project_id, month, session
        )
    )


@router.post("/{project_id}/benefits/{month}/review", response_model=ProjectWorkspaceRecord)
async def post_benefit_review(
    project_id: uuid.UUID,
    month: str,
    command: BenefitReviewCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProjectWorkspaceRecord:
    return await _plan_change(
        review_benefit_month(
            tenant.tenant_id, identity.user.id, identity.roles, project_id, month, command, session
        )
    )
