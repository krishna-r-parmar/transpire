import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.core.urls import preferences_link, tenant_frontend_url
from app.domains.audit.controllers import record_audit_event
from app.domains.audit.models import AuditEvent
from app.domains.communications.controllers import enqueue_email
from app.domains.communications.schemas import EmailMessage
from app.domains.configuration.models import ConfigurationItem
from app.domains.ideas.models import Idea, ProjectCharter
from app.domains.identity.access import can_contribute, is_workspace_admin
from app.domains.identity.models import Membership, MembershipStatus, User
from app.domains.identity.queries import contributing_membership
from app.domains.projects.models import (
    Project,
    ProjectAction,
    ProjectBenefitMonth,
    ProjectCharterBaseline,
    ProjectMilestone,
    ProjectStatus,
    ProjectTeamMember,
)
from app.domains.projects.schemas import (
    BenefitMonthCommand,
    BenefitReviewCommand,
    BenefitTrackingRecord,
    MilestoneCreateCommand,
    MilestoneMoveCommand,
    MilestonePatchCommand,
    ProjectActionRecord,
    ProjectActivityRecord,
    ProjectBaselineRecord,
    ProjectBenefitPeriodRecord,
    ProjectCharterSnapshotRecord,
    ProjectMilestonePlanCommand,
    ProjectMilestoneRecord,
    ProjectPortfolioEntry,
    ProjectTeamCandidate,
    ProjectTeamMemberRecord,
    ProjectWorkspaceRecord,
    TaskCreateCommand,
    TaskPatchCommand,
)


class ProjectNotFoundError(Exception):
    pass


class ProjectAccessError(Exception):
    pass


class ProjectValidationError(Exception):
    """A change that can't be made as sent; the message is safe to show."""


def _money(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (ValueError, TypeError):
        return Decimal(0)


def charter_snapshot(charter: ProjectCharter) -> dict[str, object]:
    return {
        "sponsor": charter.sponsor,
        "sponsor_user_id": str(charter.sponsor_user_id) if charter.sponsor_user_id else None,
        "leader": charter.leader,
        "leader_user_id": str(charter.leader_user_id) if charter.leader_user_id else None,
        "department_id": str(charter.department_id) if charter.department_id else None,
        "site_id": str(charter.site_id) if charter.site_id else None,
        "start_date": charter.start_date.isoformat() if charter.start_date else None,
        "target_completion_date": charter.target_completion_date.isoformat()
        if charter.target_completion_date
        else None,
        "team_members": charter.team_members,
        "team_membership_ids": [str(value) for value in charter.team_membership_ids],
        "in_scope": charter.in_scope,
        "out_of_scope": charter.out_of_scope,
        "objective": charter.objective,
        "benefit_type": charter.benefit_type,
        "kpi_name": charter.kpi_name,
        "budget_approved": str(charter.budget_approved)
        if charter.budget_approved is not None
        else None,
        "impact_areas": charter.impact_areas,
        "belt_level": charter.belt_level,
        "action_items": charter.action_items,
        "milestone_plan": charter.milestone_plan or [],
        "monthly_tracking": charter.monthly_tracking,
    }


async def open_project_for_approved_idea(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    idea_id: uuid.UUID,
    idea_reference: str,
    charter: ProjectCharter,
) -> Project:
    """Create the project as soon as an idea is approved, so it shows in the portfolio."""
    existing = await session.scalar(
        select(Project).where(Project.tenant_id == tenant_id, Project.idea_id == idea_id)
    )
    if existing:
        return existing
    project = Project(
        tenant_id=tenant_id,
        idea_id=idea_id,
        reference=idea_reference.replace("IDEA-", "PRJ-", 1),
        status=ProjectStatus.CHARTER_IN_PROGRESS.value,
        health="not_set",
        active_baseline_version=0,
        lead_name=charter.leader,
        target_completion_date=charter.target_completion_date,
    )
    session.add(project)
    await session.flush()
    return project


async def create_project_from_submitted_charter(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    idea_id: uuid.UUID,
    idea_reference: str,
    submitter_user_id: uuid.UUID,
    charter: ProjectCharter,
) -> Project:
    existing = await session.scalar(
        select(Project).where(Project.tenant_id == tenant_id, Project.idea_id == idea_id)
    )
    if existing and existing.status != ProjectStatus.CHARTER_IN_PROGRESS.value:
        return existing
    if existing:
        # Opened at approval; submitting the charter publishes baseline v1 and starts delivery.
        project = existing
        project.status = ProjectStatus.READY_TO_START.value
        project.active_baseline_version = 1
        project.lead_name = charter.leader
        project.target_completion_date = charter.target_completion_date
    else:
        project = Project(
            tenant_id=tenant_id,
            idea_id=idea_id,
            reference=idea_reference.replace("IDEA-", "PRJ-", 1),
            status=ProjectStatus.READY_TO_START.value,
            health="not_set",
            active_baseline_version=1,
            lead_name=charter.leader,
            target_completion_date=charter.target_completion_date,
        )
        session.add(project)
    await session.flush()
    session.add(
        ProjectCharterBaseline(
            tenant_id=tenant_id,
            project_id=project.id,
            version=1,
            snapshot=charter_snapshot(charter),
            reason="Initial submitted charter",
            created_by_user_id=submitter_user_id,
            published_at=charter.submitted_at or datetime.now(UTC),
        )
    )
    return project


async def assign_project_team(
    session: AsyncSession,
    *,
    settings: Settings,
    tenant_id: uuid.UUID,
    tenant_name: str,
    tenant_slug: str,
    project: Project,
    idea: Idea,
    members: list[tuple[Membership, User]],
) -> int:
    now = datetime.now(UTC)
    queued = 0
    for membership, user in members:
        session.add(
            ProjectTeamMember(
                tenant_id=tenant_id,
                project_id=project.id,
                membership_id=membership.id,
                user_id=user.id,
                name_snapshot=user.display_name,
                email_snapshot=user.email,
                status="invited",
                invited_at=now,
            )
        )
        enqueue_email(
            session,
            EmailMessage(
                tenant_id=tenant_id,
                recipient=user.email,
                template_key="project_team_invitation",
                subject=f"You're invited to project {project.reference}",
                template_data={
                    "recipient_name": user.display_name,
                    "tenant_name": tenant_name,
                    "project_reference": project.reference,
                    "project_title": idea.title,
                    "project_lead": project.lead_name,
                    "action_url": tenant_frontend_url(settings, tenant_slug, "/projects"),
                    "action_label": "Review project invitation",
                    **preferences_link(settings, tenant_slug),
                },
            ),
            settings,
        )
        queued += 1
    return queued


async def list_team_candidates(
    tenant_id: uuid.UUID, session: AsyncSession
) -> list[ProjectTeamCandidate]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        rows = (
            await session.execute(
                select(Membership, User)
                .join(User, User.id == Membership.user_id)
                .where(
                    Membership.tenant_id == tenant_id,
                    Membership.status == MembershipStatus.ACTIVE,
                    contributing_membership(Membership.id, tenant_id),
                )
                .order_by(User.display_name, User.email)
            )
        ).all()
        return [
            ProjectTeamCandidate(
                membership_id=membership.id,
                user_id=user.id,
                display_name=user.display_name,
                email=user.email,
            )
            for membership, user in rows
        ]


async def list_projects(tenant_id: uuid.UUID, session: AsyncSession) -> list[ProjectPortfolioEntry]:
    site = aliased(ConfigurationItem)
    department = aliased(ConfigurationItem)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        milestone_totals = (
            select(
                ProjectMilestone.project_id.label("project_id"),
                func.count(ProjectMilestone.id).label("milestone_count"),
                func.coalesce(
                    func.sum(ProjectMilestone.progress * ProjectMilestone.weight), 0
                ).label("weighted"),
                func.coalesce(func.sum(ProjectMilestone.weight), 0).label("weight"),
            )
            .where(ProjectMilestone.tenant_id == tenant_id)
            .group_by(ProjectMilestone.project_id)
            .subquery()
        )
        rows = (
            await session.execute(
                select(
                    Project,
                    Idea,
                    ProjectCharter,
                    site.name,
                    department.name,
                    milestone_totals.c.milestone_count,
                    milestone_totals.c.weighted,
                    milestone_totals.c.weight,
                )
                .join(Idea, Idea.id == Project.idea_id)
                .join(ProjectCharter, ProjectCharter.idea_id == Idea.id)
                .outerjoin(site, site.id == ProjectCharter.site_id)
                .outerjoin(department, department.id == ProjectCharter.department_id)
                .outerjoin(milestone_totals, milestone_totals.c.project_id == Project.id)
                .where(Project.tenant_id == tenant_id)
                .order_by(Project.updated_at.desc())
            )
        ).all()
        months_by_project: dict[uuid.UUID, list[ProjectBenefitMonth]] = {}
        for month in (
            await session.scalars(
                select(ProjectBenefitMonth).where(ProjectBenefitMonth.tenant_id == tenant_id)
            )
        ).all():
            months_by_project.setdefault(month.project_id, []).append(month)
        result: list[ProjectPortfolioEntry] = []
        for project, idea, charter, site_name, department_name, count, weighted, weight in rows:
            target = annual_target_lakhs(idea)
            achieved, validated, los = benefit_totals(months_by_project.get(project.id, []))
            result.append(
                ProjectPortfolioEntry(
                    id=project.id,
                    idea_id=idea.id,
                    reference=project.reference,
                    idea_reference=idea.reference,
                    title=idea.title,
                    status=project.status,
                    health=project.health,
                    lead_name=project.lead_name,
                    site=site_name,
                    department=department_name,
                    target_completion_date=project.target_completion_date,
                    baseline_version=project.active_baseline_version,
                    milestone_count=int(count or 0),
                    progress=Decimal(weighted or 0) / Decimal(weight or 1),
                    target=target,
                    achieved=achieved,
                    validated=validated,
                    line_of_sight=los,
                    projected_outcome=achieved + los,
                    updated_at=project.updated_at,
                )
            )
        return result


async def get_project_workspace(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    site = aliased(ConfigurationItem)
    department = aliased(ConfigurationItem)
    baseline_author = aliased(User)
    activity_actor = aliased(User)

    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        project_row = (
            await session.execute(
                select(Project, Idea, ProjectCharter, site.name, department.name)
                .join(Idea, Idea.id == Project.idea_id)
                .join(ProjectCharter, ProjectCharter.idea_id == Idea.id)
                .outerjoin(site, site.id == ProjectCharter.site_id)
                .outerjoin(department, department.id == ProjectCharter.department_id)
                .where(Project.tenant_id == tenant_id, Project.id == project_id)
            )
        ).one_or_none()
        if project_row is None:
            raise ProjectNotFoundError

        project, idea, charter, site_name, department_name = project_row
        milestone_rows = list(
            (
                await session.scalars(
                    select(ProjectMilestone)
                    .where(
                        ProjectMilestone.tenant_id == tenant_id,
                        ProjectMilestone.project_id == project_id,
                    )
                    .order_by(ProjectMilestone.position)
                )
            ).all()
        )
        milestone_ids = [milestone.id for milestone in milestone_rows]
        action_rows = (
            list(
                (
                    await session.scalars(
                        select(ProjectAction)
                        .where(
                            ProjectAction.tenant_id == tenant_id,
                            ProjectAction.milestone_id.in_(milestone_ids),
                        )
                        .order_by(ProjectAction.created_at)
                    )
                ).all()
            )
            if milestone_ids
            else []
        )
        actions_by_milestone: dict[uuid.UUID, list[ProjectActionRecord]] = {}
        for action in action_rows:
            actions_by_milestone.setdefault(action.milestone_id, []).append(
                ProjectActionRecord(
                    id=action.id,
                    title=action.title,
                    owner_name=action.owner_name,
                    owner_user_id=action.owner_user_id,
                    due_date=action.due_date,
                    completed_at=action.completed_at,
                    status=action.status,
                    notes=action.notes,
                )
            )

        team_rows = list(
            (
                await session.scalars(
                    select(ProjectTeamMember)
                    .where(
                        ProjectTeamMember.tenant_id == tenant_id,
                        ProjectTeamMember.project_id == project_id,
                    )
                    .order_by(ProjectTeamMember.name_snapshot)
                )
            ).all()
        )
        lead_membership = await session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == idea.submitter_user_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        can_manage_plan = can_contribute(roles) and (
            is_workspace_admin(roles)
            or user_id == idea.submitter_user_id
            or any(member.user_id == user_id for member in team_rows)
        )
        owner_candidates = []
        if lead_membership:
            lead_user = await session.get(User, idea.submitter_user_id)
            if lead_user:
                owner_candidates.append(
                    ProjectTeamCandidate(
                        membership_id=lead_membership.id,
                        user_id=lead_user.id,
                        display_name=lead_user.display_name,
                        email=lead_user.email,
                    )
                )
        for member in team_rows:
            if not any(candidate.user_id == member.user_id for candidate in owner_candidates):
                owner_candidates.append(
                    ProjectTeamCandidate(
                        membership_id=member.membership_id,
                        user_id=member.user_id,
                        display_name=member.name_snapshot,
                        email=member.email_snapshot,
                    )
                )
        baseline_rows = (
            await session.execute(
                select(ProjectCharterBaseline, baseline_author)
                .join(
                    baseline_author, baseline_author.id == ProjectCharterBaseline.created_by_user_id
                )
                .where(
                    ProjectCharterBaseline.tenant_id == tenant_id,
                    ProjectCharterBaseline.project_id == project_id,
                )
                .order_by(ProjectCharterBaseline.version.desc())
            )
        ).all()
        active_baseline = next(
            (
                baseline
                for baseline, _ in baseline_rows
                if baseline.version == project.active_baseline_version
            ),
            None,
        )
        if active_baseline is None and project.status != ProjectStatus.CHARTER_IN_PROGRESS.value:
            raise ProjectNotFoundError

        activity_rows = (
            await session.execute(
                select(AuditEvent, activity_actor)
                .outerjoin(activity_actor, activity_actor.id == AuditEvent.actor_user_id)
                .where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.entity_reference == idea.reference,
                )
                .order_by(AuditEvent.created_at.desc())
                .limit(50)
            )
        ).all()

        months = list(
            (
                await session.scalars(
                    select(ProjectBenefitMonth)
                    .where(
                        ProjectBenefitMonth.tenant_id == tenant_id,
                        ProjectBenefitMonth.project_id == project_id,
                    )
                    .order_by(ProjectBenefitMonth.month)
                )
            ).all()
        )
        benefit_periods = [benefit_period_record(month) for month in months]
        target = annual_target_lakhs(idea)
        achieved, validated, line_of_sight = benefit_totals(months)
        benefits_milestone = next((item for item in milestone_rows if item.benefits_start), None)
        benefits = BenefitTrackingRecord(
            state="open" if months else "waiting" if benefits_milestone else "unplanned",
            milestone_title=benefits_milestone.title if benefits_milestone else None,
            milestone_due=benefits_milestone.planned_end if benefits_milestone else None,
            milestone_status=benefits_milestone.status if benefits_milestone else None,
            annual_target=target,
            kpi_only=charter.benefit_type == "kpi_only",
            kpi_name=charter.kpi_name,
            kpi_baseline=" ".join(filter(None, [idea.current_state, idea.baseline_uom])),
            kpi_target=" ".join(filter(None, [idea.target_state, idea.target_uom])),
            can_record=can_manage_plan
            and project.status != ProjectStatus.CHARTER_IN_PROGRESS.value,
            can_validate=is_workspace_admin(roles),
        )
        total_weight = sum((milestone.weight for milestone in milestone_rows), Decimal(0))
        weighted_progress = sum(
            (milestone.progress * milestone.weight for milestone in milestone_rows), Decimal(0)
        )

        return ProjectWorkspaceRecord(
            id=project.id,
            idea_id=idea.id,
            reference=project.reference,
            idea_reference=idea.reference,
            title=idea.title,
            idea_type=idea.idea_type,
            project_category=idea.project_category,
            project_subtype=idea.project_subtype,
            status=project.status,
            health=project.health,
            lead_name=project.lead_name,
            site=site_name,
            department=department_name,
            start_date=charter.start_date,
            target_completion_date=project.target_completion_date,
            baseline_version=project.active_baseline_version,
            progress=(weighted_progress / total_weight if total_weight else Decimal(0)),
            target=target,
            achieved=achieved,
            validated=validated,
            line_of_sight=line_of_sight,
            projected_outcome=achieved + line_of_sight,
            charter=ProjectCharterSnapshotRecord.model_validate(
                active_baseline.snapshot if active_baseline else charter_snapshot(charter)
            ),
            benefit_periods=benefit_periods,
            benefits=benefits,
            milestones=[
                ProjectMilestoneRecord(
                    id=milestone.id,
                    position=milestone.position,
                    title=milestone.title,
                    outcome=milestone.outcome,
                    owner_name=milestone.owner_name,
                    owner_user_id=milestone.owner_user_id,
                    planned_start=milestone.planned_start,
                    planned_end=milestone.planned_end,
                    actual_start=milestone.actual_start,
                    actual_end=milestone.actual_end,
                    weight=milestone.weight,
                    progress=milestone.progress,
                    status=milestone.status,
                    completion_criteria=milestone.completion_criteria,
                    evidence=milestone.evidence,
                    dependency_ids=milestone.dependency_ids,
                    actions=actions_by_milestone.get(milestone.id, []),
                    baseline_planned_end=milestone.baseline_planned_end,
                    baseline_weight=milestone.baseline_weight,
                    benefits_start=milestone.benefits_start,
                    variance_days=(
                        (milestone.planned_end - milestone.baseline_planned_end).days
                        if milestone.planned_end and milestone.baseline_planned_end
                        else None
                    ),
                )
                for milestone in milestone_rows
            ],
            team=[
                ProjectTeamMemberRecord(
                    id=member.id,
                    name=member.name_snapshot,
                    email=member.email_snapshot,
                    status=member.status,
                    invited_at=member.invited_at,
                    responded_at=member.responded_at,
                )
                for member in team_rows
            ],
            baselines=[
                ProjectBaselineRecord(
                    id=baseline.id,
                    version=baseline.version,
                    reason=baseline.reason,
                    created_by_name=author.display_name,
                    published_at=baseline.published_at,
                    is_active=baseline.version == project.active_baseline_version,
                )
                for baseline, author in baseline_rows
            ],
            activity=[
                ProjectActivityRecord(
                    id=event.id,
                    event_type=event.event_type,
                    summary=event.summary,
                    actor_name=actor.display_name if actor else None,
                    created_at=event.created_at,
                )
                for event, actor in activity_rows
            ],
            can_manage_plan=can_manage_plan,
            owner_candidates=owner_candidates,
            updated_at=project.updated_at,
        )


async def save_milestone_plan(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    command: ProjectMilestonePlanCommand,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        project = await session.scalar(
            select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id)
        )
        if project is None:
            raise ProjectNotFoundError
        idea = await session.get(Idea, project.idea_id)
        team_user_ids = set(
            (
                await session.scalars(
                    select(ProjectTeamMember.user_id).where(
                        ProjectTeamMember.tenant_id == tenant_id,
                        ProjectTeamMember.project_id == project_id,
                    )
                )
            ).all()
        )
        if (
            not idea
            or not can_contribute(roles)
            or not (
                is_workspace_admin(roles)
                or user_id == idea.submitter_user_id
                or user_id in team_user_ids
            )
        ):
            raise ProjectAccessError
        allowed_owners = team_user_ids | {idea.submitter_user_id}
        selected_owners = {
            owner_id
            for milestone in command.milestones
            for owner_id in [milestone.owner_user_id]
            if owner_id
        } | {
            owner_id
            for milestone in command.milestones
            for action in milestone.actions
            for owner_id in [action.owner_user_id]
            if owner_id
        }
        if not selected_owners.issubset(allowed_owners):
            raise ProjectAccessError

        existing_ids = list(
            (
                await session.scalars(
                    select(ProjectMilestone.id).where(
                        ProjectMilestone.tenant_id == tenant_id,
                        ProjectMilestone.project_id == project_id,
                    )
                )
            ).all()
        )
        if existing_ids:
            await session.execute(
                delete(ProjectAction).where(
                    ProjectAction.tenant_id == tenant_id,
                    ProjectAction.milestone_id.in_(existing_ids),
                )
            )
            await session.execute(
                delete(ProjectMilestone).where(
                    ProjectMilestone.tenant_id == tenant_id,
                    ProjectMilestone.project_id == project_id,
                )
            )
        for milestone_command in command.milestones:
            milestone = ProjectMilestone(
                id=milestone_command.id,
                tenant_id=tenant_id,
                project_id=project_id,
                position=milestone_command.position,
                title=milestone_command.title,
                outcome=milestone_command.outcome,
                owner_name=milestone_command.owner_name,
                owner_user_id=milestone_command.owner_user_id,
                planned_start=milestone_command.planned_start,
                planned_end=milestone_command.planned_end,
                actual_start=milestone_command.actual_start,
                actual_end=milestone_command.actual_end,
                weight=milestone_command.weight,
                progress=milestone_command.progress,
                status=milestone_command.status,
                completion_criteria=milestone_command.completion_criteria,
                evidence=milestone_command.evidence,
                dependency_ids=milestone_command.dependency_ids,
            )
            session.add(milestone)
            for action_command in milestone_command.actions:
                session.add(
                    ProjectAction(
                        id=action_command.id,
                        tenant_id=tenant_id,
                        milestone_id=milestone.id,
                        title=action_command.title,
                        owner_name=action_command.owner_name,
                        owner_user_id=action_command.owner_user_id,
                        due_date=action_command.due_date,
                        status=action_command.status,
                        notes=action_command.notes,
                    )
                )
        if command.milestones and project.status == "ready_to_start":
            project.status = "in_progress"
            project.started_at = datetime.now(UTC)
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=idea.submitter_user_id,
            event_type="project.milestone_plan_saved",
            entity_type="project",
            entity_id=project.id,
            entity_reference=idea.reference,
            summary=f"Saved the milestone plan for {project.reference}.",
            details={"milestone_count": len(command.milestones)},
        )
        await session.flush()
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)


# --- Baseline milestones and one-at-a-time plan changes -----------------------------------------


async def create_baseline_milestones(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    project: Project,
    plan: list,
    start_date: date | None,
    allowed_owner_ids: set[uuid.UUID],
) -> None:
    """Turn the submitted charter's milestones into the project's baseline plan."""
    has_milestones = await session.scalar(
        select(func.count(ProjectMilestone.id)).where(
            ProjectMilestone.tenant_id == tenant_id, ProjectMilestone.project_id == project.id
        )
    )
    if has_milestones:
        return
    previous_end = start_date
    for position, item in enumerate(plan, start=1):
        owner_id = item.owner_user_id if item.owner_user_id in allowed_owner_ids else None
        session.add(
            ProjectMilestone(
                tenant_id=tenant_id,
                project_id=project.id,
                position=position,
                title=item.title.strip(),
                owner_user_id=owner_id,
                owner_name=item.owner_name if owner_id else "",
                planned_start=previous_end,
                planned_end=item.due_date,
                baseline_planned_end=item.due_date,
                weight=item.weight,
                baseline_weight=item.weight,
                progress=Decimal(0),
                status="not_started",
                benefits_start=item.benefits_start,
                dependency_ids=[],
            )
        )
        previous_end = item.due_date or previous_end
    await session.flush()


async def _plan_context(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
) -> tuple[Project, Idea, set[uuid.UUID]]:
    """The project, its idea, and who may own milestones; raises if the caller can't plan."""
    project = await session.scalar(
        select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id)
    )
    if project is None:
        raise ProjectNotFoundError
    idea = await session.get(Idea, project.idea_id)
    team_user_ids = set(
        (
            await session.scalars(
                select(ProjectTeamMember.user_id).where(
                    ProjectTeamMember.tenant_id == tenant_id,
                    ProjectTeamMember.project_id == project_id,
                    ProjectTeamMember.status.in_(("invited", "accepted")),
                )
            )
        ).all()
    )
    if (
        idea is None
        or not can_contribute(roles)
        or not (
            is_workspace_admin(roles)
            or user_id == idea.submitter_user_id
            or user_id in team_user_ids
        )
    ):
        raise ProjectAccessError
    if project.status == ProjectStatus.CHARTER_IN_PROGRESS.value:
        raise ProjectValidationError("Submit the charter before changing the delivery plan.")
    return project, idea, team_user_ids | {idea.submitter_user_id}


async def _milestone(
    session: AsyncSession, tenant_id: uuid.UUID, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> ProjectMilestone:
    milestone = await session.scalar(
        select(ProjectMilestone)
        .where(
            ProjectMilestone.tenant_id == tenant_id,
            ProjectMilestone.project_id == project_id,
            ProjectMilestone.id == milestone_id,
        )
        .with_for_update()
    )
    if milestone is None:
        raise ProjectNotFoundError
    return milestone


async def _owner_name(
    session: AsyncSession, owner_id: uuid.UUID | None, allowed: set[uuid.UUID]
) -> str:
    if owner_id is None:
        return ""
    if owner_id not in allowed:
        raise ProjectValidationError("Owners must be the project lead or on the project team.")
    user = await session.get(User, owner_id)
    return user.display_name if user else ""


async def _weight_total_without(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    milestone_id: uuid.UUID | None,
) -> Decimal:
    statement = select(func.coalesce(func.sum(ProjectMilestone.weight), 0)).where(
        ProjectMilestone.tenant_id == tenant_id, ProjectMilestone.project_id == project_id
    )
    if milestone_id is not None:
        statement = statement.where(ProjectMilestone.id != milestone_id)
    return Decimal(await session.scalar(statement) or 0)


def _start_delivery(project: Project) -> None:
    if project.status == ProjectStatus.READY_TO_START.value:
        project.status = ProjectStatus.IN_PROGRESS.value
        project.started_at = datetime.now(UTC)


def _plain(value: object) -> object:
    return (
        value.isoformat()
        if isinstance(value, date)
        else str(value)
        if isinstance(value, (Decimal, uuid.UUID))
        else value
    )


BASELINE_FIELDS = ("title", "planned_end", "weight")


async def update_milestone(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    command: MilestonePatchCommand,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        project, idea, owners = await _plan_context(session, tenant_id, user_id, roles, project_id)
        milestone = await _milestone(session, tenant_id, project_id, milestone_id)
        nullable = {"owner_user_id", "planned_start", "planned_end", "actual_start", "actual_end"}
        sent = {
            field: getattr(command, field)
            for field in command.model_fields_set
            if field != "reason" and (getattr(command, field) is not None or field in nullable)
        }
        changes: dict[str, list[object]] = {}
        for field, value in sent.items():
            if field == "owner_user_id":
                milestone.owner_name = await _owner_name(session, value, owners)
            if getattr(milestone, field) != value:
                changes[field] = [_plain(getattr(milestone, field)), _plain(value)]
                setattr(milestone, field, value)
        if "weight" in changes:
            total = await _weight_total_without(session, tenant_id, project_id, milestone.id)
            if total + milestone.weight > 100:
                raise ProjectValidationError(
                    f"Weights would total {(total + milestone.weight).normalize():f}%. Keep them at 100% or less."
                )
        if (
            milestone.planned_start
            and milestone.planned_end
            and milestone.planned_end < milestone.planned_start
        ):
            raise ProjectValidationError("The due date must be on or after the start date.")
        replanned = [field for field in BASELINE_FIELDS if field in changes]
        if replanned and milestone.baseline_planned_end is not None and not command.reason.strip():
            raise ProjectValidationError(
                "Say why the plan changed. Reviewers see this next to the change."
            )
        today = datetime.now(UTC).date()
        if changes.get("status") and milestone.status == "complete":
            milestone.progress = Decimal(100)
            milestone.actual_end = milestone.actual_end or today
        elif "progress" in changes and milestone.progress >= 100 and "status" not in sent:
            milestone.status = "complete"
            milestone.actual_end = milestone.actual_end or today
        elif (
            "progress" in changes
            and 0 < milestone.progress < 100
            and "status" not in sent
            and milestone.status in ("not_started", "complete")
        ):
            milestone.status = "in_progress"
            milestone.actual_end = None if "actual_end" not in sent else milestone.actual_end
        if milestone.status in ("in_progress", "complete") or milestone.progress > 0:
            milestone.actual_start = milestone.actual_start or today
            _start_delivery(project)
        if milestone.benefits_start and milestone.status == "complete":
            await open_benefit_months(
                session,
                tenant_id=tenant_id,
                project=project,
                idea=idea,
                start=milestone.actual_end or today,
            )
        if changes.get("benefits_start") and milestone.benefits_start:
            others = (
                await session.scalars(
                    select(ProjectMilestone).where(
                        ProjectMilestone.tenant_id == tenant_id,
                        ProjectMilestone.project_id == project_id,
                        ProjectMilestone.id != milestone.id,
                        ProjectMilestone.benefits_start.is_(True),
                    )
                )
            ).all()
            for other in others:
                other.benefits_start = False
        if changes:
            record_audit_event(
                session,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                subject_user_id=idea.submitter_user_id,
                event_type="milestone.replanned" if replanned else "milestone.updated",
                entity_type="project_milestone",
                entity_id=milestone.id,
                entity_reference=idea.reference,
                summary=(
                    f'Re-planned "{milestone.title}" on {project.reference}: {command.reason.strip()}'
                    if replanned and command.reason.strip()
                    else f'Updated "{milestone.title}" on {project.reference}.'
                ),
                details={"changes": changes, "reason": command.reason.strip() or None},
            )
        await session.flush()
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)


async def add_milestone(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    command: MilestoneCreateCommand,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        project, idea, owners = await _plan_context(session, tenant_id, user_id, roles, project_id)
        has_baseline = project.active_baseline_version >= 1
        if has_baseline and not command.reason.strip():
            raise ProjectValidationError("Say why this milestone is being added to the plan.")
        total = await _weight_total_without(session, tenant_id, project_id, None)
        if total + command.weight > 100:
            raise ProjectValidationError(
                f"Weights would total {(total + command.weight).normalize():f}%. Lower another milestone first."
            )
        last = await session.scalar(
            select(func.coalesce(func.max(ProjectMilestone.position), 0)).where(
                ProjectMilestone.tenant_id == tenant_id, ProjectMilestone.project_id == project_id
            )
        )
        milestone = ProjectMilestone(
            tenant_id=tenant_id,
            project_id=project_id,
            position=int(last or 0) + 1,
            title=command.title.strip(),
            owner_user_id=command.owner_user_id,
            owner_name=await _owner_name(session, command.owner_user_id, owners),
            planned_end=command.planned_end,
            weight=command.weight,
            progress=Decimal(0),
            status="not_started",
            dependency_ids=[],
        )
        session.add(milestone)
        await session.flush()
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=idea.submitter_user_id,
            event_type="milestone.added",
            entity_type="project_milestone",
            entity_id=milestone.id,
            entity_reference=idea.reference,
            summary=(
                f'Added "{milestone.title}" to {project.reference}'
                + (f": {command.reason.strip()}" if command.reason.strip() else ".")
            ),
            details={"reason": command.reason.strip() or None, "after_baseline": has_baseline},
        )
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)


async def remove_milestone(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    reason: str,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        project, idea, _ = await _plan_context(session, tenant_id, user_id, roles, project_id)
        milestone = await _milestone(session, tenant_id, project_id, milestone_id)
        if milestone.baseline_planned_end is not None and not reason.strip():
            raise ProjectValidationError("Say why this charter milestone is being removed.")
        title, position = milestone.title, milestone.position
        await session.delete(milestone)
        await session.flush()
        later = (
            await session.scalars(
                select(ProjectMilestone)
                .where(
                    ProjectMilestone.tenant_id == tenant_id,
                    ProjectMilestone.project_id == project_id,
                    ProjectMilestone.position > position,
                )
                .order_by(ProjectMilestone.position)
            )
        ).all()
        for item in later:
            item.position -= 1
            await session.flush()
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=idea.submitter_user_id,
            event_type="milestone.removed",
            entity_type="project_milestone",
            entity_id=milestone_id,
            entity_reference=idea.reference,
            summary=f'Removed "{title}" from {project.reference}'
            + (f": {reason.strip()}" if reason.strip() else "."),
            details={"reason": reason.strip() or None},
        )
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)


async def move_milestone(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    command: MilestoneMoveCommand,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        await _plan_context(session, tenant_id, user_id, roles, project_id)
        milestone = await _milestone(session, tenant_id, project_id, milestone_id)
        target = milestone.position + (-1 if command.direction == "up" else 1)
        neighbour = await session.scalar(
            select(ProjectMilestone)
            .where(
                ProjectMilestone.tenant_id == tenant_id,
                ProjectMilestone.project_id == project_id,
                ProjectMilestone.position == target,
            )
            .with_for_update()
        )
        if neighbour is not None:
            # Positions are unique, so park one milestone while the two swap.
            original = milestone.position
            milestone.position = 0
            await session.flush()
            neighbour.position = original
            await session.flush()
            milestone.position = target
            await session.flush()
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)


async def add_task(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    command: TaskCreateCommand,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        project, _, owners = await _plan_context(session, tenant_id, user_id, roles, project_id)
        milestone = await _milestone(session, tenant_id, project_id, milestone_id)
        session.add(
            ProjectAction(
                tenant_id=tenant_id,
                milestone_id=milestone.id,
                title=command.title.strip(),
                owner_user_id=command.owner_user_id,
                owner_name=await _owner_name(session, command.owner_user_id, owners),
                due_date=command.due_date,
                status="not_started",
                notes="",
            )
        )
        _start_delivery(project)
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)


async def update_task(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    task_id: uuid.UUID,
    command: TaskPatchCommand,
    session: AsyncSession,
    *,
    delete_task: bool = False,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        project, _, owners = await _plan_context(session, tenant_id, user_id, roles, project_id)
        await _milestone(session, tenant_id, project_id, milestone_id)
        task = await session.scalar(
            select(ProjectAction).where(
                ProjectAction.tenant_id == tenant_id,
                ProjectAction.milestone_id == milestone_id,
                ProjectAction.id == task_id,
            )
        )
        if task is None:
            raise ProjectNotFoundError
        if delete_task:
            await session.delete(task)
        else:
            for field in command.model_fields_set:
                value = getattr(command, field)
                if value is None and field not in ("owner_user_id", "due_date"):
                    continue
                if field == "owner_user_id":
                    task.owner_name = await _owner_name(session, value, owners)
                setattr(task, field, value)
            if "status" in command.model_fields_set:
                task.completed_at = datetime.now(UTC) if task.status == "complete" else None
                _start_delivery(project)
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)


# --- Benefits in delivery --------------------------------------------------------------------

BENEFIT_MONTHS = 12
LAKH = Decimal(100000)


def annual_target_lakhs(idea: Idea) -> Decimal:
    """The yearly benefit the approved idea promised, in ₹ lakhs (saving plus cost avoidance)."""
    total = (idea.estimated_annual_saving or Decimal(0)) + (idea.cost_avoidance or Decimal(0))
    return (Decimal(total) / LAKH).quantize(Decimal("0.01"))


def benefit_totals(months: list[ProjectBenefitMonth]) -> tuple[Decimal, Decimal, Decimal]:
    """Achieved, Finance-validated, and line-of-sight totals across recorded months."""
    achieved = sum((month.actual or Decimal(0) for month in months), Decimal(0))
    validated = sum(
        (month.actual or Decimal(0) for month in months if month.finance_status == "validated"),
        Decimal(0),
    )
    line_of_sight = sum((month.line_of_sight or Decimal(0) for month in months), Decimal(0))
    return achieved, validated, line_of_sight


def benefit_period_record(month: ProjectBenefitMonth) -> ProjectBenefitPeriodRecord:
    return ProjectBenefitPeriodRecord(
        month=month.month.strftime("%Y-%m"),
        plan=month.plan,
        achieved=month.actual or Decimal(0),
        has_actual=month.actual is not None,
        line_of_sight=month.line_of_sight or Decimal(0),
        kpi_actual=month.kpi_actual,
        status=month.status,
        notes=month.notes,
        finance_approved=month.finance_status == "validated",
        finance_status=month.finance_status,
        finance_comment=month.finance_comment,
    )


def first_of_month(value: date) -> date:
    return value.replace(day=1)


def add_months(value: date, count: int) -> date:
    index = value.month - 1 + count
    return date(value.year + index // 12, index % 12 + 1, 1)


def monthly_plan(annual: Decimal) -> list[Decimal]:
    """Spread the yearly target across twelve months; the last month takes the rounding."""
    each = (annual / BENEFIT_MONTHS).quantize(Decimal("0.01"))
    return [each] * (BENEFIT_MONTHS - 1) + [annual - each * (BENEFIT_MONTHS - 1)]


async def open_benefit_months(
    session: AsyncSession, *, tenant_id: uuid.UUID, project: Project, idea: Idea, start: date
) -> None:
    """Open twelve months of tracking from the month the benefits milestone completed."""
    existing = await session.scalar(
        select(func.count(ProjectBenefitMonth.id)).where(
            ProjectBenefitMonth.tenant_id == tenant_id, ProjectBenefitMonth.project_id == project.id
        )
    )
    if existing:
        return
    first = first_of_month(start)
    for offset, plan in enumerate(monthly_plan(annual_target_lakhs(idea))):
        session.add(
            ProjectBenefitMonth(
                tenant_id=tenant_id,
                project_id=project.id,
                month=add_months(first, offset),
                plan=plan,
                status="",
                notes="",
                finance_status="open",
                finance_comment="",
            )
        )
    record_audit_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=None,
        subject_user_id=idea.submitter_user_id,
        event_type="benefits.opened",
        entity_type="project",
        entity_id=project.id,
        entity_reference=idea.reference,
        summary=f"Benefit tracking opened for {project.reference} from {first:%b %Y}.",
        details={"first_month": first.isoformat()},
    )
    await session.flush()


def _parse_month(value: str) -> date:
    try:
        return date.fromisoformat(f"{value}-01")
    except ValueError as error:
        raise ProjectNotFoundError from error


async def _benefit_month(
    session: AsyncSession, tenant_id: uuid.UUID, project_id: uuid.UUID, month: str
) -> ProjectBenefitMonth:
    row = await session.scalar(
        select(ProjectBenefitMonth)
        .where(
            ProjectBenefitMonth.tenant_id == tenant_id,
            ProjectBenefitMonth.project_id == project_id,
            ProjectBenefitMonth.month == _parse_month(month),
        )
        .with_for_update()
    )
    if row is None:
        raise ProjectNotFoundError
    return row


async def record_benefit_month(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    month: str,
    command: BenefitMonthCommand,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        await _plan_context(session, tenant_id, user_id, roles, project_id)
        row = await _benefit_month(session, tenant_id, project_id, month)
        if row.finance_status in ("submitted", "validated"):
            raise ProjectValidationError(
                "This month is with Finance. It can change again if Finance challenges it."
            )
        sent = command.model_fields_set
        future = row.month > first_of_month(datetime.now(UTC).date())
        if future and sent & {"actual", "kpi_actual", "status"}:
            raise ProjectValidationError("Actuals can be recorded once the month has started.")
        for field in sent:
            value = getattr(command, field)
            if value is None and field in ("plan", "status", "notes"):
                continue
            setattr(row, field, value)
        await session.flush()
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)


async def submit_benefit_month(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    month: str,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        project, idea, _ = await _plan_context(session, tenant_id, user_id, roles, project_id)
        row = await _benefit_month(session, tenant_id, project_id, month)
        if row.finance_status not in ("open", "challenged"):
            raise ProjectValidationError("This month has already been sent to Finance.")
        if row.actual is None:
            raise ProjectValidationError("Record the actual benefit before sending it to Finance.")
        row.finance_status = "submitted"
        row.submitted_by_user_id = user_id
        row.submitted_at = datetime.now(UTC)
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=idea.submitter_user_id,
            event_type="benefits.submitted",
            entity_type="project",
            entity_id=project.id,
            entity_reference=idea.reference,
            summary=f"Sent {row.month:%b %Y} benefits ({row.actual} L) to Finance for {project.reference}.",
            details={"month": row.month.isoformat(), "actual": str(row.actual)},
        )
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)


async def review_benefit_month(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    project_id: uuid.UUID,
    month: str,
    command: BenefitReviewCommand,
    session: AsyncSession,
) -> ProjectWorkspaceRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        if not is_workspace_admin(roles):
            raise ProjectAccessError
        project = await session.scalar(
            select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id)
        )
        if project is None:
            raise ProjectNotFoundError
        idea = await session.get(Idea, project.idea_id)
        row = await _benefit_month(session, tenant_id, project_id, month)
        if row.finance_status != "submitted":
            raise ProjectValidationError("Only months sent to Finance can be reviewed.")
        if command.decision == "challenge" and not command.comment.strip():
            raise ProjectValidationError("Say what needs to change so the project lead can fix it.")
        row.finance_status = "validated" if command.decision == "validate" else "challenged"
        row.finance_comment = command.comment.strip()
        row.reviewed_by_user_id = user_id
        row.reviewed_at = datetime.now(UTC)
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=idea.submitter_user_id if idea else None,
            event_type=f"benefits.{row.finance_status}",
            entity_type="project",
            entity_id=project.id,
            entity_reference=idea.reference if idea else project.reference,
            summary=(
                f"Finance {'validated' if command.decision == 'validate' else 'challenged'} "
                f"{row.month:%b %Y} benefits for {project.reference}"
                + (f": {row.finance_comment}" if row.finance_comment else ".")
            ),
            details={"month": row.month.isoformat(), "comment": row.finance_comment or None},
        )
    return await get_project_workspace(tenant_id, user_id, roles, project_id, session)
