import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.core.urls import tenant_frontend_url
from app.domains.audit.controllers import record_audit_event
from app.domains.audit.models import AuditEvent
from app.domains.communications.controllers import enqueue_email
from app.domains.communications.schemas import EmailMessage
from app.domains.configuration.models import ConfigurationItem
from app.domains.ideas.models import Idea, ProjectCharter
from app.domains.identity.models import Membership, MembershipStatus, User
from app.domains.projects.models import (
    Project,
    ProjectAction,
    ProjectCharterBaseline,
    ProjectMilestone,
    ProjectTeamMember,
)
from app.domains.projects.schemas import (
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
)


class ProjectNotFoundError(Exception):
    pass


class ProjectAccessError(Exception):
    pass


def _money(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (ValueError, TypeError):
        return Decimal(0)


def charter_snapshot(charter: ProjectCharter) -> dict[str, object]:
    return {
        "sponsor": charter.sponsor,
        "leader": charter.leader,
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
        "monthly_tracking": charter.monthly_tracking,
    }


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
    if existing:
        return existing
    project = Project(
        tenant_id=tenant_id,
        idea_id=idea_id,
        reference=idea_reference.replace("IDEA-", "PRJ-", 1),
        status="ready_to_start",
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
                subject=f"You are invited to project {project.reference}",
                template_data={
                    "recipient_name": user.display_name,
                    "tenant_name": tenant_name,
                    "project_reference": project.reference,
                    "project_title": idea.title,
                    "project_lead": project.lead_name,
                    "action_url": tenant_frontend_url(settings, tenant_slug, "/projects"),
                    "action_label": "Review project invitation",
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
        result: list[ProjectPortfolioEntry] = []
        for project, idea, charter, site_name, department_name, count, weighted, weight in rows:
            entries = charter.monthly_tracking or []
            target = sum((_money(entry.get("ftm_plan")) for entry in entries), Decimal(0))
            achieved = sum((_money(entry.get("ftm_actual")) for entry in entries), Decimal(0))
            validated = sum(
                (
                    _money(entry.get("ftm_actual"))
                    for entry in entries
                    if entry.get("finance_approved")
                ),
                Decimal(0),
            )
            los = sum((_money(entry.get("line_of_sight")) for entry in entries), Decimal(0))
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
        can_manage_plan = (
            "tenant_admin" in roles
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
                .join(baseline_author, baseline_author.id == ProjectCharterBaseline.created_by_user_id)
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
        if active_baseline is None:
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

        benefit_periods = [
            ProjectBenefitPeriodRecord(
                month=str(entry.get("month") or ""),
                plan=_money(entry.get("ftm_plan")),
                achieved=_money(entry.get("ftm_actual")),
                line_of_sight=_money(entry.get("line_of_sight")),
                kpi_actual=(
                    _money(entry.get("kpi_actual"))
                    if entry.get("kpi_actual") not in (None, "")
                    else None
                ),
                status=str(entry.get("status") or ""),
                finance_approved=bool(entry.get("finance_approved")),
            )
            for entry in (charter.monthly_tracking or [])
        ]
        target = sum((entry.plan for entry in benefit_periods), Decimal(0))
        achieved = sum((entry.achieved for entry in benefit_periods), Decimal(0))
        validated = sum(
            (entry.achieved for entry in benefit_periods if entry.finance_approved), Decimal(0)
        )
        line_of_sight = sum(
            (entry.line_of_sight for entry in benefit_periods), Decimal(0)
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
            charter=ProjectCharterSnapshotRecord.model_validate(active_baseline.snapshot or {}),
            benefit_periods=benefit_periods,
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
        if not idea or not (
            "tenant_admin" in roles or user_id == idea.submitter_user_id or user_id in team_user_ids
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
