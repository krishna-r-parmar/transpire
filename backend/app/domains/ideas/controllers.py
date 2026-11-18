import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.core.urls import preferences_link, tenant_frontend_url
from app.domains.audit.controllers import record_audit_event
from app.domains.communications.controllers import enqueue_email
from app.domains.communications.schemas import EmailMessage
from app.domains.configuration.models import (
    ConfigurationItem,
    DepartmentSite,
    WorkflowDefinition,
    WorkflowVersion,
    WorkflowVersionStatus,
)
from app.domains.ideas.fx import ExchangeRateUnavailableError, get_inr_usd_rate
from app.domains.ideas.models import (
    Idea,
    IdeaApprovalStage,
    IdeaBankPolicy,
    IdeaJoinRequest,
    IdeaStatus,
    JoinRequestStatus,
    ProjectCharter,
)
from app.domains.ideas.repositories import SQLAlchemyIdeaRepository
from app.domains.ideas.schemas import (
    ApprovalContractPreview,
    ApprovalDecisionCommand,
    ApprovalStagePreview,
    ApprovalStageRecord,
    ApprovalWorkItem,
    CatalogItem,
    CharterIdeaContext,
    CharterMilestone,
    CharterWorkspaceRecord,
    EditableIdeaRecord,
    HomeIdeaSummary,
    HomeWorkspaceSummary,
    IdeaBankEntry,
    IdeaBankPolicyCommand,
    IdeaBankPolicySummary,
    IdeaDetailRecord,
    IdeaJourneyStage,
    IdeaRecord,
    IdeaSubmissionCatalog,
    IdeaSummaryRecord,
    IdeaUpsertCommand,
    JoinRequestCommand,
    JoinRequestRecord,
    JoinState,
    ProjectCharterCommand,
    ProjectCharterRecord,
)
from app.domains.identity.access import ADMIN_ROLE_KEYS, can_contribute, is_workspace_admin
from app.domains.identity.models import Membership, MembershipStatus, Role, User, membership_roles
from app.domains.projects.controllers import (
    assign_project_team,
    create_baseline_milestones,
    create_project_from_submitted_charter,
    open_project_for_approved_idea,
)
from app.domains.projects.models import Project, ProjectTeamMember
from app.domains.tenants.models import Tenant


class IdeaNotFoundError(Exception):
    pass


class IdeaValidationError(Exception):
    pass


class IdeaAccessError(Exception):
    pass


repository = SQLAlchemyIdeaRepository()


def _reference() -> str:
    return f"IDEA-{datetime.now(UTC).year}-{uuid.uuid4().hex[:8].upper()}"


def _record(idea: Idea) -> IdeaRecord:
    return IdeaRecord(
        id=idea.id,
        reference=idea.reference,
        status=idea.status.value,
        idea_type=idea.idea_type,
        title=idea.title,
        category_id=idea.category_id,
        subcategory_id=idea.subcategory_id,
        process_area_id=idea.process_area_id,
        impacts=idea.impacts,
        updated_at=idea.updated_at,
        submitted_at=idea.submitted_at,
        draft_step=idea.draft_step,
    )


def _editable_record(idea: Idea, correction_reason: str | None = None) -> EditableIdeaRecord:
    return EditableIdeaRecord(
        id=idea.id,
        reference=idea.reference,
        status=idea.status.value,
        updated_at=idea.updated_at,
        correction_reason=correction_reason,
        draft_step=idea.draft_step,
        idea_type=idea.idea_type,
        project_category=idea.project_category,
        project_subtype=idea.project_subtype,
        site_id=idea.site_id,
        department_id=idea.department_id,
        category_id=idea.category_id,
        subcategory_id=idea.subcategory_id,
        process_area_id=idea.process_area_id,
        title=idea.title,
        problem_statement=idea.problem_statement,
        business_case=idea.business_case,
        current_state=idea.current_state,
        baseline_uom=idea.baseline_uom,
        target_state=idea.target_state,
        target_uom=idea.target_uom,
        target_completion_date=idea.target_completion_date,
        impacts=idea.impacts,
        estimated_annual_saving=idea.estimated_annual_saving,
        cost_avoidance=idea.cost_avoidance,
        investment_required=idea.investment_required,
    )


def _as_usd(value: Decimal | None, rate: Decimal | None) -> Decimal | None:
    if value is None or rate is None:
        return None
    return (value * rate).quantize(Decimal("0.01"))


def _charter_record(charter: ProjectCharter) -> ProjectCharterRecord:
    return ProjectCharterRecord(
        id=charter.id,
        sponsor=charter.sponsor,
        leader=charter.leader,
        sponsor_user_id=charter.sponsor_user_id,
        leader_user_id=charter.leader_user_id,
        department_id=charter.department_id,
        site_id=charter.site_id,
        start_date=charter.start_date,
        target_completion_date=charter.target_completion_date,
        team_members=charter.team_members,
        team_membership_ids=charter.team_membership_ids,
        in_scope=charter.in_scope,
        out_of_scope=charter.out_of_scope,
        objective=charter.objective,
        benefit_type=charter.benefit_type,
        kpi_name=charter.kpi_name,
        budget_approved=charter.budget_approved,
        impact_areas=charter.impact_areas,
        belt_level=charter.belt_level,
        action_items=charter.action_items,
        milestone_plan=charter.milestone_plan or [],
        monthly_tracking=charter.monthly_tracking,
        status="submitted" if charter.submitted_at else "draft",
        updated_at=charter.updated_at,
        submitted_at=charter.submitted_at,
    )


async def _resolve_fallback_approver(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[Membership, User] | None:
    return (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .join(membership_roles, membership_roles.c.membership_id == Membership.id)
            .join(Role, Role.id == membership_roles.c.role_id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.status == MembershipStatus.ACTIVE,
                Role.tenant_id == tenant_id,
                Role.key.in_(ADMIN_ROLE_KEYS),
            )
            .order_by(User.display_name)
            .limit(1)
        )
    ).first()


async def _instantiate_approval_stages(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    idea: Idea,
    version: WorkflowVersion,
    round_number: int = 1,
) -> None:
    fallback = await _resolve_fallback_approver(session, tenant_id)
    now = datetime.now(UTC)
    for index, stage in enumerate(version.stages):
        membership = None
        user = None
        membership_id = stage.get("assignee_membership_id")
        if membership_id:
            row = (
                await session.execute(
                    select(Membership, User)
                    .join(User, User.id == Membership.user_id)
                    .where(
                        Membership.tenant_id == tenant_id,
                        Membership.id == uuid.UUID(str(membership_id)),
                        Membership.status.in_([MembershipStatus.ACTIVE, MembershipStatus.INVITED]),
                    )
                    .limit(1)
                )
            ).first()
            if row:
                membership, user = row
        if membership is None or user is None:
            if fallback is None:
                raise IdeaValidationError("The approval contract has no available approver.")
            membership, user = fallback
        sla_hours = int(stage.get("sla_hours", 48))
        session.add(
            IdeaApprovalStage(
                tenant_id=tenant_id,
                idea_id=idea.id,
                round_number=round_number,
                stage_order=index + 1,
                stage_key=str(stage.get("key", f"stage_{index + 1}")),
                stage_name=str(stage.get("name", f"Approval stage {index + 1}")),
                assignee_membership_id=membership.id,
                assignee_user_id=user.id,
                assignee_name=user.display_name,
                assignee_email=user.email,
                sla_hours=sla_hours,
                status="pending" if index == 0 else "waiting",
                due_at=now + timedelta(hours=sla_hours) if index == 0 else None,
            )
        )


async def _validate_catalog(
    session: AsyncSession, tenant_id: uuid.UUID, command: IdeaUpsertCommand
) -> None:
    expected = {
        "site": command.site_id,
        "department": command.department_id,
        "category": command.category_id,
        "subcategory": command.subcategory_id,
        "process_area": command.process_area_id,
    }
    identifiers = [identifier for identifier in expected.values() if identifier]
    if not identifiers:
        return
    records = list(
        (
            await session.scalars(
                select(ConfigurationItem).where(
                    ConfigurationItem.tenant_id == tenant_id,
                    ConfigurationItem.id.in_(identifiers),
                    ConfigurationItem.is_active.is_(True),
                )
            )
        ).all()
    )
    by_id = {record.id: record for record in records}
    for kind, identifier in expected.items():
        if identifier and (identifier not in by_id or by_id[identifier].kind != kind):
            raise IdeaValidationError(f"Select an active {kind.replace('_', ' ')}.")
    if command.department_id:
        department = by_id[command.department_id]
        if command.site_id is None:
            raise IdeaValidationError("Select a site for the department.")
        assigned = department.applies_to_all_sites or bool(
            await session.scalar(
                select(DepartmentSite.id).where(
                    DepartmentSite.tenant_id == tenant_id,
                    DepartmentSite.department_id == command.department_id,
                    DepartmentSite.site_id == command.site_id,
                )
            )
        )
        if not assigned and department.parent_id != command.site_id:
            raise IdeaValidationError("The selected department does not belong to that site.")
    if command.subcategory_id and by_id[command.subcategory_id].parent_id != command.category_id:
        raise IdeaValidationError("The selected subcategory does not belong to that category.")


def _apply(idea: Idea, command: IdeaUpsertCommand) -> None:
    for field, value in command.model_dump().items():
        setattr(idea, field, value)


def _validate_required_submission(command: IdeaUpsertCommand) -> None:
    missing = []
    for label, value in (
        ("category", command.category_id),
        ("subcategory", command.subcategory_id),
        ("title", command.title.strip()),
        ("problem statement", command.problem_statement.strip()),
        ("business case", command.business_case.strip()),
        ("impact", command.impacts),
    ):
        if not value:
            missing.append(label)
    if missing:
        raise IdeaValidationError(f"Complete the required fields: {', '.join(missing)}.")


async def save_idea(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    command: IdeaUpsertCommand,
    session: AsyncSession,
    idea_id: uuid.UUID | None = None,
) -> IdeaRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        await _validate_catalog(session, tenant_id, command)
        created = idea_id is None
        if idea_id:
            idea = await repository.get_editable(session, tenant_id, idea_id, user_id)
            if idea is None:
                raise IdeaNotFoundError
        else:
            idea = Idea(
                tenant_id=tenant_id,
                submitter_user_id=user_id,
                reference=_reference(),
                status=IdeaStatus.DRAFT,
            )
            session.add(idea)
        _apply(idea, command)
        await session.flush()
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=user_id,
            event_type=(
                "idea.draft_created"
                if created
                else "idea.correction_updated"
                if idea.status == IdeaStatus.NEEDS_CORRECTION
                else "idea.draft_updated"
            ),
            entity_type="idea",
            entity_id=idea.id,
            entity_reference=idea.reference,
            summary=(
                f"Created draft {idea.reference}."
                if created
                else f"Updated {idea.reference} at submission step {idea.draft_step}."
            ),
            details={"status": idea.status.value, "draft_step": idea.draft_step},
        )
        await session.refresh(idea)
        return _record(idea)


async def submit_idea(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    idea_id: uuid.UUID,
    command: IdeaUpsertCommand,
    session: AsyncSession,
    settings: Settings | None = None,
) -> IdeaRecord:
    return await _submit_editable_idea(
        tenant_id, user_id, idea_id, command, session, settings, expected=IdeaStatus.DRAFT
    )


async def resubmit_idea(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    idea_id: uuid.UUID,
    command: IdeaUpsertCommand,
    session: AsyncSession,
    settings: Settings | None = None,
) -> IdeaRecord:
    return await _submit_editable_idea(
        tenant_id,
        user_id,
        idea_id,
        command,
        session,
        settings,
        expected=IdeaStatus.NEEDS_CORRECTION,
    )


async def _submit_editable_idea(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    idea_id: uuid.UUID,
    command: IdeaUpsertCommand,
    session: AsyncSession,
    settings: Settings | None,
    *,
    expected: IdeaStatus,
) -> IdeaRecord:
    _validate_required_submission(command)
    fx_rate = None
    if settings is not None:
        try:
            fx_rate = await get_inr_usd_rate(settings)
        except ExchangeRateUnavailableError:
            pass
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        await _validate_catalog(session, tenant_id, command)
        idea = await repository.get_editable(session, tenant_id, idea_id, user_id)
        if idea is None or idea.status != expected:
            raise IdeaNotFoundError
        if expected == IdeaStatus.NEEDS_CORRECTION:
            workflow_version = await session.scalar(
                select(WorkflowVersion).where(
                    WorkflowVersion.tenant_id == tenant_id,
                    WorkflowVersion.id == idea.workflow_version_id,
                )
            )
        else:
            workflow_version = await session.scalar(
                select(WorkflowVersion)
                .where(
                    WorkflowVersion.tenant_id == tenant_id,
                    WorkflowVersion.status == WorkflowVersionStatus.PUBLISHED,
                )
                .limit(1)
            )
        if workflow_version is None:
            if expected == IdeaStatus.NEEDS_CORRECTION:
                raise IdeaValidationError("The captured approval contract is no longer available.")
            raise IdeaValidationError("No published approval contract is available.")
        round_number = (
            int(
                await session.scalar(
                    select(func.coalesce(func.max(IdeaApprovalStage.round_number), 0)).where(
                        IdeaApprovalStage.tenant_id == tenant_id,
                        IdeaApprovalStage.idea_id == idea.id,
                    )
                )
                or 0
            )
            + 1
        )
        _apply(idea, command)
        idea.workflow_version_id = workflow_version.id
        idea.status = IdeaStatus.SUBMITTED
        if idea.submitted_at is None:
            idea.submitted_at = datetime.now(UTC)
        if fx_rate is not None:
            idea.usd_exchange_rate = fx_rate.rate
            idea.fx_rate_date = fx_rate.rate_date
        await session.flush()
        await _instantiate_approval_stages(
            session, tenant_id, idea, workflow_version, round_number=round_number
        )
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=user_id,
            event_type=(
                "idea.resubmitted" if expected == IdeaStatus.NEEDS_CORRECTION else "idea.submitted"
            ),
            entity_type="idea",
            entity_id=idea.id,
            entity_reference=idea.reference,
            summary=(
                f"Resubmitted {idea.reference} for approval round {round_number}."
                if expected == IdeaStatus.NEEDS_CORRECTION
                else f"Submitted {idea.reference} for approval."
            ),
            details={
                "approval_round": round_number,
                "workflow_version_id": str(workflow_version.id),
            },
        )
        await session.refresh(idea)
        return _record(idea)


async def get_editable_idea(
    tenant_id: uuid.UUID, user_id: uuid.UUID, idea_id: uuid.UUID, session: AsyncSession
) -> EditableIdeaRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        idea = await repository.get_editable(session, tenant_id, idea_id, user_id)
        if idea is None:
            raise IdeaNotFoundError
        correction_reason = await session.scalar(
            select(IdeaApprovalStage.decision_comment)
            .where(
                IdeaApprovalStage.tenant_id == tenant_id,
                IdeaApprovalStage.idea_id == idea_id,
                IdeaApprovalStage.status == "needs_correction",
            )
            .order_by(IdeaApprovalStage.round_number.desc(), IdeaApprovalStage.stage_order.desc())
            .limit(1)
        )
        return _editable_record(idea, correction_reason)


async def delete_draft_idea(
    tenant_id: uuid.UUID, user_id: uuid.UUID, idea_id: uuid.UUID, session: AsyncSession
) -> None:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        idea = await repository.get_draft(session, tenant_id, idea_id, user_id)
        if idea is None:
            raise IdeaNotFoundError
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=user_id,
            event_type="idea.draft_deleted",
            entity_type="idea",
            entity_id=idea.id,
            entity_reference=idea.reference,
            summary=f"Deleted draft {idea.reference}.",
            details={"title": idea.title},
        )
        await session.delete(idea)


# Ideas anyone in the workspace can find in the Idea Bank. Drafts, corrections, rejections and
# withdrawals stay private to their owner, approvers and Workspace Admins.
BANK_STATUSES = frozenset(
    {
        IdeaStatus.SUBMITTED,
        IdeaStatus.APPROVED,
        IdeaStatus.CHARTER_IN_PROGRESS,
        IdeaStatus.CHARTER_SUBMITTED,
    }
)


@dataclass(frozen=True)
class BankVisibility:
    """Which Idea Bank fields a viewer may see, derived from the tenant's visibility policy."""

    operational: bool
    narrative: bool
    contributor: bool
    financials: bool

    @classmethod
    def from_policy(cls, policy: IdeaBankPolicy) -> "BankVisibility":
        return cls(
            operational=policy.detail_level in {"operational", "full"},
            narrative=policy.detail_level == "full",
            contributor=True,  # Owner and team names are always shown.
            financials=bool(policy.show_financials),
        )

    @classmethod
    def everything(cls) -> "BankVisibility":
        return cls(operational=True, narrative=True, contributor=True, financials=True)


def bank_entry_fields(
    idea: Idea,
    contributor: str | None,
    category: str | None,
    subcategory: str | None,
    process_area: str | None,
    visibility: BankVisibility,
) -> dict:
    """Idea Bank fields for one idea, with everything the policy hides set to None."""
    operational, full, money = visibility.operational, visibility.narrative, visibility.financials
    return {
        "id": idea.id,
        "reference": idea.reference,
        "title": idea.title,
        "status": idea.status.value,
        "idea_type": idea.idea_type,
        "category": category,
        "submitted_at": idea.submitted_at,
        "contributor": contributor if visibility.contributor else None,
        "subcategory": subcategory if operational else None,
        "process_area": process_area if operational else None,
        "impacts": idea.impacts if operational else None,
        "current_state": idea.current_state if operational else None,
        "baseline_uom": idea.baseline_uom if operational else None,
        "target_state": idea.target_state if operational else None,
        "target_uom": idea.target_uom if operational else None,
        "problem_statement": idea.problem_statement if full else None,
        "business_case": idea.business_case if full else None,
        "estimated_annual_saving": idea.estimated_annual_saving if money else None,
        "cost_avoidance": idea.cost_avoidance if money else None,
        "investment_required": idea.investment_required if money else None,
        "estimated_annual_saving_usd": (
            _as_usd(idea.estimated_annual_saving, idea.usd_exchange_rate) if money else None
        ),
        "cost_avoidance_usd": _as_usd(idea.cost_avoidance, idea.usd_exchange_rate)
        if money
        else None,
        "investment_required_usd": (
            _as_usd(idea.investment_required, idea.usd_exchange_rate) if money else None
        ),
        "usd_exchange_rate": idea.usd_exchange_rate if money else None,
        "fx_rate_date": idea.fx_rate_date if money else None,
    }


def can_manage_idea(
    idea: Idea, stages: list[IdeaApprovalStage], user_id: uuid.UUID, roles: list[str]
) -> bool:
    """Owner, any assigned approver, or a Workspace Admin: the people who may open the full record."""
    return (
        idea.submitter_user_id == user_id
        or any(stage.assignee_user_id == user_id for stage in stages)
        or is_workspace_admin(roles)
    )


async def _bank_policy(session: AsyncSession, tenant_id: uuid.UUID) -> IdeaBankPolicy:
    policy = await repository.get_policy(session, tenant_id)
    if policy is None:
        policy = IdeaBankPolicy(tenant_id=tenant_id)
        session.add(policy)
        await session.flush()
    return policy


async def list_idea_bank(tenant_id: uuid.UUID, session: AsyncSession) -> list[IdeaBankEntry]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        visibility = BankVisibility.from_policy(await _bank_policy(session, tenant_id))
        rows = await repository.list_bank(session, tenant_id)
        teams = await team_names_by_idea(session, tenant_id, [row[0].id for row in rows])
        return [
            IdeaBankEntry(**bank_entry_fields(*row, visibility), team=teams.get(row[0].id, []))
            for row in rows
        ]


async def get_idea_summary(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    idea_id: uuid.UUID,
    session: AsyncSession,
) -> IdeaSummaryRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        row = await repository.get_summary_row(session, tenant_id, idea_id)
        if row is None:
            raise IdeaNotFoundError
        idea, contributor, category, subcategory, process_area, site, department = row
        stages = list(
            (
                await session.scalars(
                    select(IdeaApprovalStage)
                    .where(
                        IdeaApprovalStage.tenant_id == tenant_id,
                        IdeaApprovalStage.idea_id == idea_id,
                    )
                    .order_by(IdeaApprovalStage.round_number, IdeaApprovalStage.stage_order)
                )
            ).all()
        )
        manager = can_manage_idea(idea, stages, user_id, roles)
        if not manager and idea.status not in BANK_STATUSES:
            raise IdeaAccessError
        visibility = (
            BankVisibility.everything()
            if manager
            else BankVisibility.from_policy(await _bank_policy(session, tenant_id))
        )
        teams = await team_names_by_idea(session, tenant_id, [idea.id])
        join_state = await viewer_join_state(session, tenant_id, idea, user_id, roles)
        is_owner_or_admin = idea.submitter_user_id == user_id or is_workspace_admin(roles)
        join_requests = (
            await pending_join_requests(session, tenant_id, idea_ids=[idea.id])
            if is_owner_or_admin
            else []
        )
        return IdeaSummaryRecord(
            **bank_entry_fields(idea, contributor, category, subcategory, process_area, visibility),
            team=teams.get(idea.id, []),
            join_state=join_state,
            join_requests=join_requests,
            site=site if visibility.operational else None,
            department=department if visibility.operational else None,
            approval_journey=[
                IdeaJourneyStage(
                    stage_name=stage.stage_name,
                    status=stage.status,
                    round_number=stage.round_number,
                    stage_order=stage.stage_order,
                )
                for stage in stages
            ],
            charter_available=idea.status
            in {IdeaStatus.APPROVED, IdeaStatus.CHARTER_IN_PROGRESS, IdeaStatus.CHARTER_SUBMITTED},
            charter_submitted=idea.status == IdeaStatus.CHARTER_SUBMITTED,
            can_manage=manager,
            shows_operational=visibility.operational,
            shows_narrative=visibility.narrative,
            shows_contributor=visibility.contributor,
            shows_financials=visibility.financials,
        )


async def get_catalog(tenant_id: uuid.UUID, session: AsyncSession) -> IdeaSubmissionCatalog:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        grouped: dict[str, list[CatalogItem]] = {
            "site": [],
            "department": [],
            "category": [],
            "subcategory": [],
            "process_area": [],
        }
        items = await repository.get_catalog_items(session, tenant_id)
        department_ids = [item.id for item in items if item.kind == "department"]
        scope_rows = (
            (
                await session.execute(
                    select(DepartmentSite.department_id, DepartmentSite.site_id).where(
                        DepartmentSite.tenant_id == tenant_id,
                        DepartmentSite.department_id.in_(department_ids),
                    )
                )
            ).all()
            if department_ids
            else []
        )
        site_ids_by_department: dict[uuid.UUID, list[uuid.UUID]] = {}
        for department_id, site_id in scope_rows:
            site_ids_by_department.setdefault(department_id, []).append(site_id)
        for item in items:
            grouped[item.kind].append(
                CatalogItem(
                    id=item.id,
                    code=item.code,
                    name=item.name,
                    parent_id=item.parent_id,
                    site_ids=site_ids_by_department.get(item.id, []),
                    applies_to_all_sites=item.applies_to_all_sites,
                    guidance=item.guidance,
                )
            )
        workflow_row = (
            await session.execute(
                select(WorkflowDefinition, WorkflowVersion)
                .join(WorkflowVersion, WorkflowVersion.workflow_id == WorkflowDefinition.id)
                .where(
                    WorkflowDefinition.tenant_id == tenant_id,
                    WorkflowDefinition.is_active.is_(True),
                    WorkflowVersion.tenant_id == tenant_id,
                    WorkflowVersion.status == WorkflowVersionStatus.PUBLISHED,
                )
                .order_by(
                    WorkflowVersion.published_at.desc().nullslast(), WorkflowVersion.version.desc()
                )
                .limit(1)
            )
        ).first()
        approval_contract = None
        if workflow_row:
            definition, version = workflow_row
            approval_contract = ApprovalContractPreview(
                id=version.id,
                name=definition.name,
                description=definition.description,
                version=version.version,
                stages=[
                    ApprovalStagePreview(
                        key=str(stage.get("key", f"stage_{index + 1}")),
                        name=str(stage.get("name", f"Approval stage {index + 1}")),
                        approver_role=str(stage.get("approver_role", "tenant_admin")),
                        assignee_name=stage.get("assignee_name"),
                        assignee_email=stage.get("assignee_email"),
                        assignee_status=stage.get("assignee_status"),
                        sla_hours=int(stage.get("sla_hours", 48)),
                        required=bool(stage.get("required", True)),
                    )
                    for index, stage in enumerate(version.stages)
                ],
            )
        return IdeaSubmissionCatalog(
            sites=grouped["site"],
            departments=grouped["department"],
            categories=grouped["category"],
            subcategories=grouped["subcategory"],
            process_areas=grouped["process_area"],
            approval_contract=approval_contract,
        )


async def get_idea_bank_policy(
    tenant_id: uuid.UUID, session: AsyncSession
) -> IdeaBankPolicySummary:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        policy = await repository.get_policy(session, tenant_id)
        if policy is None:
            policy = IdeaBankPolicy(tenant_id=tenant_id)
            session.add(policy)
            await session.flush()
        return IdeaBankPolicySummary(
            detail_level=policy.detail_level,
            show_financials=policy.show_financials,
        )


async def update_idea_bank_policy(
    tenant_id: uuid.UUID, command: IdeaBankPolicyCommand, session: AsyncSession
) -> IdeaBankPolicySummary:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        policy = await repository.get_policy(session, tenant_id, lock=True)
        if policy is None:
            policy = IdeaBankPolicy(tenant_id=tenant_id)
            session.add(policy)
        policy.detail_level = command.detail_level
        policy.show_financials = command.show_financials
        await session.flush()
        return IdeaBankPolicySummary(**command.model_dump())


async def get_home_workspace(
    tenant_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> HomeWorkspaceSummary:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        ideas = list(
            (
                await session.scalars(
                    select(Idea)
                    .where(Idea.tenant_id == tenant_id, Idea.submitter_user_id == user_id)
                    .order_by(Idea.updated_at.desc())
                )
            ).all()
        )
        idea_ids = [idea.id for idea in ideas]
        stages = (
            list(
                (
                    await session.scalars(
                        select(IdeaApprovalStage)
                        .where(
                            IdeaApprovalStage.tenant_id == tenant_id,
                            IdeaApprovalStage.idea_id.in_(idea_ids),
                        )
                        .order_by(IdeaApprovalStage.round_number, IdeaApprovalStage.stage_order)
                    )
                ).all()
            )
            if idea_ids
            else []
        )
        current_stage_by_idea: dict[uuid.UUID, str] = {}
        for stage in stages:
            if stage.status == "pending":
                current_stage_by_idea[stage.idea_id] = stage.stage_name
            elif stage.status == "waiting":
                current_stage_by_idea.setdefault(stage.idea_id, stage.stage_name)
        charters = (
            list(
                (
                    await session.scalars(
                        select(ProjectCharter).where(
                            ProjectCharter.tenant_id == tenant_id,
                            ProjectCharter.idea_id.in_(idea_ids),
                        )
                    )
                ).all()
            )
            if idea_ids
            else []
        )
        charter_by_idea = {charter.idea_id: charter for charter in charters}
        correction_reason_by_idea: dict[uuid.UUID, str] = {}
        for stage in stages:
            if stage.status == "needs_correction" and stage.decision_comment:
                correction_reason_by_idea[stage.idea_id] = stage.decision_comment
        approval_rows = (
            await session.execute(
                select(IdeaApprovalStage, Idea, User.display_name)
                .join(Idea, Idea.id == IdeaApprovalStage.idea_id)
                .join(User, User.id == Idea.submitter_user_id)
                .where(
                    IdeaApprovalStage.tenant_id == tenant_id,
                    IdeaApprovalStage.assignee_user_id == user_id,
                    IdeaApprovalStage.status == "pending",
                )
                .order_by(IdeaApprovalStage.due_at.asc().nullslast())
            )
        ).all()
        my_idea_ids = [idea.id for idea in ideas]
        join_requests = await pending_join_requests(session, tenant_id, idea_ids=my_idea_ids)
        return HomeWorkspaceSummary(
            join_requests=join_requests,
            ideas=[
                HomeIdeaSummary(
                    id=idea.id,
                    reference=idea.reference,
                    title=idea.title or "Untitled draft",
                    idea_type=idea.idea_type,
                    status=idea.status.value,
                    submitted_at=idea.submitted_at,
                    updated_at=idea.updated_at,
                    current_stage=current_stage_by_idea.get(idea.id),
                    charter_available=idea.status
                    in {
                        IdeaStatus.APPROVED,
                        IdeaStatus.CHARTER_IN_PROGRESS,
                        IdeaStatus.CHARTER_SUBMITTED,
                    },
                    charter_status=(
                        "submitted"
                        if charter_by_idea.get(idea.id) and charter_by_idea[idea.id].submitted_at
                        else "draft"
                        if charter_by_idea.get(idea.id)
                        else None
                    ),
                    can_edit_idea=idea.status
                    in {
                        IdeaStatus.DRAFT,
                        IdeaStatus.NEEDS_CORRECTION,
                    },
                    can_delete_draft=idea.status == IdeaStatus.DRAFT,
                    correction_reason=correction_reason_by_idea.get(idea.id),
                )
                for idea in ideas
            ],
            approval_items=[
                ApprovalWorkItem(
                    idea_id=idea.id,
                    reference=idea.reference,
                    title=idea.title,
                    idea_type=idea.idea_type,
                    stage_id=stage.id,
                    stage_name=stage.stage_name,
                    submitted_by=submitter_name,
                    submitted_at=idea.submitted_at,
                    due_at=stage.due_at,
                )
                for stage, idea, submitter_name in approval_rows
            ],
        )


async def get_idea_detail(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    idea_id: uuid.UUID,
    session: AsyncSession,
) -> IdeaDetailRecord:
    site = aliased(ConfigurationItem)
    department = aliased(ConfigurationItem)
    category = aliased(ConfigurationItem)
    subcategory = aliased(ConfigurationItem)
    process_area = aliased(ConfigurationItem)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        row = (
            await session.execute(
                select(
                    Idea,
                    User.display_name,
                    User.email,
                    site.name,
                    department.name,
                    category.name,
                    subcategory.name,
                    process_area.name,
                )
                .join(User, User.id == Idea.submitter_user_id)
                .outerjoin(site, site.id == Idea.site_id)
                .outerjoin(department, department.id == Idea.department_id)
                .outerjoin(category, category.id == Idea.category_id)
                .outerjoin(subcategory, subcategory.id == Idea.subcategory_id)
                .outerjoin(process_area, process_area.id == Idea.process_area_id)
                .where(Idea.tenant_id == tenant_id, Idea.id == idea_id)
            )
        ).first()
        if row is None:
            raise IdeaNotFoundError
        (
            idea,
            submitter_name,
            submitter_email,
            site_name,
            department_name,
            category_name,
            subcategory_name,
            process_area_name,
        ) = row
        stages = list(
            (
                await session.scalars(
                    select(IdeaApprovalStage)
                    .where(
                        IdeaApprovalStage.tenant_id == tenant_id,
                        IdeaApprovalStage.idea_id == idea_id,
                    )
                    .order_by(IdeaApprovalStage.round_number, IdeaApprovalStage.stage_order)
                )
            ).all()
        )
        is_submitter = idea.submitter_user_id == user_id
        # The full record ignores the Idea Bank visibility policy, so it is limited to the people who
        # manage the idea. Everyone else reads the policy-filtered summary (get_idea_summary).
        if not can_manage_idea(idea, stages, user_id, roles):
            raise IdeaAccessError
        charter = await session.scalar(
            select(ProjectCharter).where(
                ProjectCharter.tenant_id == tenant_id,
                ProjectCharter.idea_id == idea_id,
            )
        )
        charter_available = idea.status in {
            IdeaStatus.APPROVED,
            IdeaStatus.CHARTER_IN_PROGRESS,
            IdeaStatus.CHARTER_SUBMITTED,
        }
        correction_reason = next(
            (
                stage.decision_comment
                for stage in reversed(stages)
                if stage.status == "needs_correction" and stage.decision_comment
            ),
            None,
        )
        return IdeaDetailRecord(
            id=idea.id,
            reference=idea.reference,
            status=idea.status.value,
            idea_type=idea.idea_type,
            project_category=idea.project_category,
            project_subtype=idea.project_subtype,
            title=idea.title,
            submitter_name=submitter_name,
            submitter_email=submitter_email,
            submitted_at=idea.submitted_at,
            updated_at=idea.updated_at,
            site_id=idea.site_id,
            site=site_name,
            department_id=idea.department_id,
            department=department_name,
            category=category_name,
            subcategory=subcategory_name,
            process_area=process_area_name,
            problem_statement=idea.problem_statement,
            business_case=idea.business_case,
            current_state=idea.current_state,
            baseline_uom=idea.baseline_uom,
            target_state=idea.target_state,
            target_uom=idea.target_uom,
            impacts=idea.impacts,
            estimated_annual_saving=idea.estimated_annual_saving,
            cost_avoidance=idea.cost_avoidance,
            investment_required=idea.investment_required,
            estimated_annual_saving_usd=_as_usd(
                idea.estimated_annual_saving, idea.usd_exchange_rate
            ),
            cost_avoidance_usd=_as_usd(idea.cost_avoidance, idea.usd_exchange_rate),
            investment_required_usd=_as_usd(idea.investment_required, idea.usd_exchange_rate),
            usd_exchange_rate=idea.usd_exchange_rate,
            fx_rate_date=idea.fx_rate_date,
            approval_stages=[
                ApprovalStageRecord(
                    id=stage.id,
                    round_number=stage.round_number,
                    stage_order=stage.stage_order,
                    stage_key=stage.stage_key,
                    stage_name=stage.stage_name,
                    assignee_name=stage.assignee_name,
                    assignee_email=stage.assignee_email,
                    sla_hours=stage.sla_hours,
                    status=stage.status,
                    decision_comment=stage.decision_comment,
                    due_at=stage.due_at,
                    actioned_at=stage.actioned_at,
                    is_actionable=stage.assignee_user_id == user_id and stage.status == "pending",
                )
                for stage in stages
            ],
            charter_available=charter_available,
            charter=_charter_record(charter) if charter else None,
            project_id=await session.scalar(
                select(Project.id).where(Project.tenant_id == tenant_id, Project.idea_id == idea.id)
            ),
            can_edit_charter=is_submitter
            and charter_available
            and idea.status != IdeaStatus.CHARTER_SUBMITTED,
            can_edit_idea=is_submitter
            and idea.status in {IdeaStatus.DRAFT, IdeaStatus.NEEDS_CORRECTION},
            correction_reason=correction_reason,
        )


async def decide_approval_stage(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    idea_id: uuid.UUID,
    stage_id: uuid.UUID,
    command: ApprovalDecisionCommand,
    settings: Settings,
    session: AsyncSession,
) -> IdeaDetailRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        stage = await session.scalar(
            select(IdeaApprovalStage)
            .where(
                IdeaApprovalStage.tenant_id == tenant_id,
                IdeaApprovalStage.id == stage_id,
                IdeaApprovalStage.idea_id == idea_id,
            )
            .with_for_update()
        )
        if stage is None:
            raise IdeaNotFoundError
        if stage.assignee_user_id != user_id:
            raise IdeaAccessError
        if stage.status != "pending":
            raise IdeaValidationError("This approval item is no longer pending.")
        idea = await session.scalar(
            select(Idea).where(Idea.tenant_id == tenant_id, Idea.id == idea_id).with_for_update()
        )
        if idea is None:
            raise IdeaNotFoundError
        if idea.status != IdeaStatus.SUBMITTED:
            raise IdeaValidationError("This idea is no longer awaiting approval.")
        now = datetime.now(UTC)
        stage.status = command.decision
        stage.decision_comment = command.comment.strip() or None
        stage.actioned_at = now
        if command.decision == "approve":
            next_stage = await session.scalar(
                select(IdeaApprovalStage)
                .where(
                    IdeaApprovalStage.tenant_id == tenant_id,
                    IdeaApprovalStage.idea_id == idea_id,
                    IdeaApprovalStage.round_number == stage.round_number,
                    IdeaApprovalStage.stage_order > stage.stage_order,
                    IdeaApprovalStage.status == "waiting",
                )
                .order_by(IdeaApprovalStage.stage_order)
                .limit(1)
                .with_for_update()
            )
            if next_stage:
                next_stage.status = "pending"
                next_stage.due_at = now + timedelta(hours=next_stage.sla_hours)
            else:
                idea.status = IdeaStatus.APPROVED
                submitter = await session.get(User, idea.submitter_user_id)
                charter = prefilled_charter(
                    idea,
                    leader=submitter,
                    kpi_hint=await _subcategory_kpi(session, tenant_id, idea.subcategory_id),
                )
                session.add(charter)
                await session.flush()
                await open_project_for_approved_idea(
                    session,
                    tenant_id=tenant_id,
                    idea_id=idea.id,
                    idea_reference=idea.reference,
                    charter=charter,
                )
                tenant_record = await session.get(Tenant, tenant_id)
                if submitter:
                    enqueue_email(
                        session,
                        EmailMessage(
                            tenant_id=tenant_id,
                            recipient=submitter.email,
                            template_key="project_charter_ready",
                            subject=f"Your idea {idea.reference} is approved",
                            template_data={
                                "recipient_name": submitter.display_name,
                                "tenant_name": tenant_record.name
                                if tenant_record
                                else "your organisation",
                                "idea_reference": idea.reference,
                                "idea_title": idea.title,
                                "action_url": tenant_frontend_url(
                                    settings,
                                    tenant_record.slug if tenant_record else "",
                                    f"/ideas/{idea.id}",
                                    query={"section": "project-charter"},
                                ),
                                "action_label": "Complete project charter",
                                **preferences_link(
                                    settings, tenant_record.slug if tenant_record else ""
                                ),
                            },
                        ),
                        settings,
                    )
        else:
            idea.status = (
                IdeaStatus.NEEDS_CORRECTION
                if command.decision == "needs_correction"
                else IdeaStatus.REJECTED
            )
            waiting_stages = list(
                (
                    await session.scalars(
                        select(IdeaApprovalStage).where(
                            IdeaApprovalStage.tenant_id == tenant_id,
                            IdeaApprovalStage.idea_id == idea_id,
                            IdeaApprovalStage.round_number == stage.round_number,
                            IdeaApprovalStage.status == "waiting",
                        )
                    )
                ).all()
            )
            for waiting in waiting_stages:
                waiting.status = "cancelled"
        action_label = {
            "approve": "approved",
            "needs_correction": "returned for correction",
            "reject": "rejected",
        }[command.decision]
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=idea.submitter_user_id,
            event_type=f"idea.approval_{command.decision}",
            entity_type="idea",
            entity_id=idea.id,
            entity_reference=idea.reference,
            summary=f"{idea.reference} was {action_label} at {stage.stage_name}.",
            details={
                "approval_round": stage.round_number,
                "stage_order": stage.stage_order,
                "stage_name": stage.stage_name,
                "comment": command.comment.strip(),
            },
        )
        await session.flush()
    return await get_idea_detail(tenant_id, user_id, [], idea_id, session)


async def save_project_charter(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    idea_id: uuid.UUID,
    command: ProjectCharterCommand,
    settings: Settings,
    session: AsyncSession,
    *,
    submit: bool = False,
    autosave: bool = False,
) -> ProjectCharterRecord:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        idea = await session.scalar(
            select(Idea).where(Idea.tenant_id == tenant_id, Idea.id == idea_id).with_for_update()
        )
        if idea is None:
            raise IdeaNotFoundError
        if idea.submitter_user_id != user_id:
            raise IdeaAccessError
        if idea.status not in {
            IdeaStatus.APPROVED,
            IdeaStatus.CHARTER_IN_PROGRESS,
            IdeaStatus.CHARTER_SUBMITTED,
        }:
            raise IdeaValidationError("The project charter opens after the idea is fully approved.")
        if idea.status == IdeaStatus.CHARTER_SUBMITTED:
            raise IdeaValidationError("The submitted project charter is read-only.")
        await _validate_catalog(
            session,
            tenant_id,
            IdeaUpsertCommand(site_id=command.site_id, department_id=command.department_id),
        )
        charter = await session.scalar(
            select(ProjectCharter)
            .where(
                ProjectCharter.tenant_id == tenant_id,
                ProjectCharter.idea_id == idea_id,
            )
            .with_for_update()
        )
        if charter is None:
            charter = ProjectCharter(tenant_id=tenant_id, idea_id=idea_id)
            session.add(charter)
        selected_members: list[tuple[Membership, User]] = []
        if command.team_membership_ids:
            selected_members = list(
                (
                    await session.execute(
                        select(Membership, User)
                        .join(User, User.id == Membership.user_id)
                        .where(
                            Membership.tenant_id == tenant_id,
                            Membership.id.in_(command.team_membership_ids),
                            Membership.status == MembershipStatus.ACTIVE,
                        )
                        .order_by(User.display_name)
                    )
                ).all()
            )
        valid_membership_ids = [membership.id for membership, _ in selected_members]
        # Action items and the monthly tracker move to delivery; keep what exists unless sent.
        payload = command.model_dump(
            exclude={
                field
                for field in ("action_items", "monthly_tracking", "milestone_plan")
                if field not in command.model_fields_set
            }
        )
        if "milestone_plan" in payload:
            # JSONB needs plain JSON values (no dates, decimals or UUIDs).
            payload["milestone_plan"] = [
                milestone.model_dump(mode="json") for milestone in command.milestone_plan
            ]
        for role in ("sponsor", "leader"):
            person_id = payload.get(f"{role}_user_id")
            if person_id is None:
                continue
            person = await _active_member_user(session, tenant_id, person_id)
            if person is None:
                raise IdeaValidationError(f"Choose an active workspace member as the {role}.")
            payload[role] = person.display_name
        payload["team_membership_ids"] = valid_membership_ids
        if selected_members:
            selected_names = [user.display_name for _, user in selected_members]
            payload["team_members"] = list(dict.fromkeys([*selected_names, *command.team_members]))
        for field, value in payload.items():
            setattr(charter, field, value)
        invitations_queued = 0
        invitations_skipped = len(command.team_membership_ids) - len(valid_membership_ids)
        if submit:
            # Site and department are only required once the workspace has set them up.
            has_sites = await _has_active_catalog_items(session, tenant_id, "site")
            has_departments = await _has_active_catalog_items(session, tenant_id, "department")
            required = {
                "sponsor or facilitator": command.sponsor.strip(),
                "project or team leader": command.leader.strip(),
                "department": command.department_id if has_departments else True,
                "site": command.site_id if has_sites else True,
                "start date": command.start_date,
                "target completion": command.target_completion_date,
                "KPI or metric": command.kpi_name.strip(),
            }
            if idea.idea_type == "project":
                required.update(
                    {
                        "in scope": command.in_scope.strip(),
                        "out of scope": command.out_of_scope.strip(),
                        "SMART objective": command.objective.strip(),
                    }
                )
            missing = [label for label, value in required.items() if not value]
            if missing:
                raise IdeaValidationError(
                    f"Complete the charter before submission: {', '.join(missing)}."
                )
            plan = [CharterMilestone.model_validate(item) for item in charter.milestone_plan or []]
            problems = milestone_plan_problems(
                plan, command.start_date, command.target_completion_date, command.benefit_type
            )
            if problems:
                raise IdeaValidationError(f"Fix the milestone plan: {' '.join(problems)}")
            charter.submitted_at = datetime.now(UTC)
            idea.status = IdeaStatus.CHARTER_SUBMITTED
            await session.flush()
            project = await create_project_from_submitted_charter(
                session,
                tenant_id=tenant_id,
                idea_id=idea.id,
                idea_reference=idea.reference,
                submitter_user_id=idea.submitter_user_id,
                charter=charter,
            )
            tenant_record = await session.get(Tenant, tenant_id)
            invitations_queued = await assign_project_team(
                session,
                settings=settings,
                tenant_id=tenant_id,
                tenant_name=tenant_record.name if tenant_record else "your organisation",
                tenant_slug=tenant_record.slug if tenant_record else "",
                project=project,
                idea=idea,
                members=selected_members,
            )
            await create_baseline_milestones(
                session,
                tenant_id=tenant_id,
                project=project,
                plan=plan,
                start_date=command.start_date,
                allowed_owner_ids={
                    idea.submitter_user_id,
                    *(user.id for _, user in selected_members),
                    *([charter.leader_user_id] if charter.leader_user_id else []),
                },
            )
        elif idea.status == IdeaStatus.APPROVED:
            idea.status = IdeaStatus.CHARTER_IN_PROGRESS
        if autosave and not submit:
            await session.flush()
            await session.refresh(charter)
            return _charter_record(charter)
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=idea.submitter_user_id,
            event_type="charter.submitted" if submit else "charter.saved",
            entity_type="project_charter",
            entity_id=charter.id,
            entity_reference=idea.reference,
            summary=(
                f"Submitted the project charter for {idea.reference}."
                if submit
                else f"Saved the project charter for {idea.reference}."
            ),
            details={"idea_id": str(idea.id)},
        )
        await session.flush()
        await session.refresh(charter)
        return _charter_record(charter).model_copy(
            update={
                "team_invitations_queued": invitations_queued,
                "team_invitations_skipped": invitations_skipped,
            }
        )


# --- Teams and requests to join -------------------------------------------------------------

# Ideas people may ask to join: approved and heading into, or already in, delivery.
JOINABLE_STATUSES = frozenset(
    {IdeaStatus.APPROVED, IdeaStatus.CHARTER_IN_PROGRESS, IdeaStatus.CHARTER_SUBMITTED}
)
ACTIVE_TEAM_STATUSES = ("invited", "accepted")


class JoinRequestError(Exception):
    """A request to join that cannot be made or decided; the message is safe to show."""


async def team_names_by_idea(
    session: AsyncSession, tenant_id: uuid.UUID, idea_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Charter team names, then project team names, de-duplicated in order, for each idea."""
    if not idea_ids:
        return {}
    teams: dict[uuid.UUID, list[str]] = {}
    for idea_id, names in (
        await session.execute(
            select(ProjectCharter.idea_id, ProjectCharter.team_members).where(
                ProjectCharter.tenant_id == tenant_id, ProjectCharter.idea_id.in_(idea_ids)
            )
        )
    ).all():
        teams.setdefault(idea_id, []).extend(name for name in names if name.strip())
    for idea_id, name in (
        await session.execute(
            select(Project.idea_id, ProjectTeamMember.name_snapshot)
            .join(ProjectTeamMember, ProjectTeamMember.project_id == Project.id)
            .where(
                Project.tenant_id == tenant_id,
                Project.idea_id.in_(idea_ids),
                ProjectTeamMember.status.in_(ACTIVE_TEAM_STATUSES),
            )
            .order_by(ProjectTeamMember.invited_at)
        )
    ).all():
        teams.setdefault(idea_id, []).append(name)
    return {idea_id: list(dict.fromkeys(names)) for idea_id, names in teams.items()}


async def _active_membership(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> Membership | None:
    return await session.scalar(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )


async def _is_team_member(
    session: AsyncSession, tenant_id: uuid.UUID, idea: Idea, user_id: uuid.UUID
) -> bool:
    membership = await _active_membership(session, tenant_id, user_id)
    if membership is not None:
        team_ids = await session.scalar(
            select(ProjectCharter.team_membership_ids).where(
                ProjectCharter.tenant_id == tenant_id, ProjectCharter.idea_id == idea.id
            )
        )
        if team_ids and membership.id in team_ids:
            return True
    on_project = await session.scalar(
        select(ProjectTeamMember.id)
        .join(Project, Project.id == ProjectTeamMember.project_id)
        .where(
            Project.tenant_id == tenant_id,
            Project.idea_id == idea.id,
            ProjectTeamMember.user_id == user_id,
            ProjectTeamMember.status.in_(ACTIVE_TEAM_STATUSES),
        )
        .limit(1)
    )
    return on_project is not None


def join_state_for(
    *,
    is_owner: bool,
    is_member: bool,
    has_pending: bool,
    joinable: bool,
    may_contribute: bool,
) -> JoinState:
    """The viewer's relationship to an idea's team, in priority order."""
    if is_owner:
        return "owner"
    if is_member:
        return "member"
    if has_pending:
        return "pending"
    if not joinable:
        return "closed"
    if not may_contribute:
        return "not_allowed"
    return "available"


async def viewer_join_state(
    session: AsyncSession, tenant_id: uuid.UUID, idea: Idea, user_id: uuid.UUID, roles: list[str]
) -> JoinState:
    pending = await session.scalar(
        select(IdeaJoinRequest.id).where(
            IdeaJoinRequest.tenant_id == tenant_id,
            IdeaJoinRequest.idea_id == idea.id,
            IdeaJoinRequest.requester_user_id == user_id,
            IdeaJoinRequest.status == JoinRequestStatus.PENDING.value,
        )
    )
    return join_state_for(
        is_owner=idea.submitter_user_id == user_id,
        is_member=await _is_team_member(session, tenant_id, idea, user_id),
        has_pending=pending is not None,
        joinable=idea.status in JOINABLE_STATUSES,
        may_contribute=can_contribute(roles),
    )


async def pending_join_requests(
    session: AsyncSession, tenant_id: uuid.UUID, *, idea_ids: list[uuid.UUID]
) -> list[JoinRequestRecord]:
    if not idea_ids:
        return []
    rows = (
        await session.execute(
            select(IdeaJoinRequest, Idea.reference, Idea.title, User.display_name, User.email)
            .join(Idea, Idea.id == IdeaJoinRequest.idea_id)
            .join(User, User.id == IdeaJoinRequest.requester_user_id)
            .where(
                IdeaJoinRequest.tenant_id == tenant_id,
                IdeaJoinRequest.idea_id.in_(idea_ids),
                IdeaJoinRequest.status == JoinRequestStatus.PENDING.value,
            )
            .order_by(IdeaJoinRequest.created_at)
        )
    ).all()
    return [
        JoinRequestRecord(
            id=request.id,
            idea_id=request.idea_id,
            idea_reference=reference,
            idea_title=title,
            requester_name=name,
            requester_email=email,
            message=request.message,
            status=request.status,
            created_at=request.created_at,
        )
        for request, reference, title, name, email in rows
    ]


async def request_to_join(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    idea_id: uuid.UUID,
    command: JoinRequestCommand,
    session: AsyncSession,
) -> JoinState:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        idea = await session.scalar(
            select(Idea).where(Idea.tenant_id == tenant_id, Idea.id == idea_id)
        )
        if idea is None:
            raise IdeaNotFoundError
        state = await viewer_join_state(session, tenant_id, idea, user_id, roles)
        if state != "available":
            raise JoinRequestError(
                {
                    "owner": "You already own this idea.",
                    "member": "You're already on this team.",
                    "pending": "You've already asked to join. The owner will reply soon.",
                    "closed": "You can ask to join once the idea is approved.",
                    "not_allowed": "Viewers can't join improvement teams.",
                }[state]
            )
        membership = await _active_membership(session, tenant_id, user_id)
        if membership is None:
            raise IdeaAccessError
        request = IdeaJoinRequest(
            tenant_id=tenant_id,
            idea_id=idea.id,
            requester_user_id=user_id,
            membership_id=membership.id,
            message=command.message.strip(),
        )
        session.add(request)
        await session.flush()
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=idea.submitter_user_id,
            event_type="idea.join_requested",
            entity_type="idea",
            entity_id=idea.id,
            entity_reference=idea.reference,
            summary=f"Asked to join the team for {idea.reference}.",
            details={"request_id": str(request.id)},
        )
        return "pending"


async def withdraw_join_request(
    tenant_id: uuid.UUID, user_id: uuid.UUID, idea_id: uuid.UUID, session: AsyncSession
) -> None:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        request = await session.scalar(
            select(IdeaJoinRequest)
            .where(
                IdeaJoinRequest.tenant_id == tenant_id,
                IdeaJoinRequest.idea_id == idea_id,
                IdeaJoinRequest.requester_user_id == user_id,
                IdeaJoinRequest.status == JoinRequestStatus.PENDING.value,
            )
            .with_for_update()
        )
        if request is None:
            raise IdeaNotFoundError
        request.status = JoinRequestStatus.WITHDRAWN.value
        request.decided_at = datetime.now(UTC)


async def decide_join_request(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    idea_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    accept: bool,
    session: AsyncSession,
) -> None:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        idea = await session.scalar(
            select(Idea).where(Idea.tenant_id == tenant_id, Idea.id == idea_id).with_for_update()
        )
        if idea is None:
            raise IdeaNotFoundError
        if idea.submitter_user_id != user_id and not is_workspace_admin(roles):
            raise IdeaAccessError
        request = await session.scalar(
            select(IdeaJoinRequest)
            .where(
                IdeaJoinRequest.tenant_id == tenant_id,
                IdeaJoinRequest.idea_id == idea_id,
                IdeaJoinRequest.id == request_id,
            )
            .with_for_update()
        )
        if request is None:
            raise IdeaNotFoundError
        if request.status != JoinRequestStatus.PENDING.value:
            raise JoinRequestError("This request has already been answered.")
        requester = await session.get(User, request.requester_user_id)
        membership = await session.get(Membership, request.membership_id)
        if accept:
            if idea.status not in JOINABLE_STATUSES:
                raise JoinRequestError("This idea is no longer taking new team members.")
            if (
                requester is None
                or membership is None
                or membership.status != MembershipStatus.ACTIVE
            ):
                raise JoinRequestError("This person no longer has access to the workspace.")
            await _add_to_team(session, tenant_id, idea, membership, requester)
        request.status = (
            JoinRequestStatus.ACCEPTED if accept else JoinRequestStatus.DECLINED
        ).value
        request.decided_by_user_id = user_id
        request.decided_at = datetime.now(UTC)
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=request.requester_user_id,
            event_type="idea.join_accepted" if accept else "idea.join_declined",
            entity_type="idea",
            entity_id=idea.id,
            entity_reference=idea.reference,
            summary=(
                f"{'Added' if accept else 'Declined'} "
                f"{requester.display_name if requester else 'a colleague'} "
                f"{'to' if accept else 'for'} the team for {idea.reference}."
            ),
            details={"request_id": str(request.id)},
        )


async def _add_to_team(
    session: AsyncSession, tenant_id: uuid.UUID, idea: Idea, membership: Membership, user: User
) -> None:
    """Charter team before delivery starts; the project team once the charter is submitted."""
    if idea.status == IdeaStatus.CHARTER_SUBMITTED:
        project = await session.scalar(
            select(Project).where(Project.tenant_id == tenant_id, Project.idea_id == idea.id)
        )
        if project is None:
            raise JoinRequestError("The project for this idea could not be found.")
        existing = await session.scalar(
            select(ProjectTeamMember).where(
                ProjectTeamMember.project_id == project.id,
                ProjectTeamMember.membership_id == membership.id,
            )
        )
        now = datetime.now(UTC)
        if existing is None:
            session.add(
                ProjectTeamMember(
                    tenant_id=tenant_id,
                    project_id=project.id,
                    membership_id=membership.id,
                    user_id=user.id,
                    name_snapshot=user.display_name,
                    email_snapshot=user.email,
                    status="accepted",
                    invited_at=now,
                    responded_at=now,
                )
            )
        else:
            existing.status, existing.responded_at = "accepted", now
        return
    charter = await session.scalar(
        select(ProjectCharter)
        .where(ProjectCharter.tenant_id == tenant_id, ProjectCharter.idea_id == idea.id)
        .with_for_update()
    )
    if charter is None:
        charter = ProjectCharter(tenant_id=tenant_id, idea_id=idea.id)
        session.add(charter)
    if membership.id not in (charter.team_membership_ids or []):
        charter.team_membership_ids = [*(charter.team_membership_ids or []), membership.id]
    names = list(charter.team_members or [])
    if user.display_name not in names:
        charter.team_members = [*names, user.display_name]


# --- Project charter ---------------------------------------------------------------------------


def benefit_type_for(saving: Decimal | None, avoidance: Decimal | None) -> str:
    """The charter's benefit type, read from the money the idea estimated."""
    has_saving, has_avoidance = bool(saving and saving > 0), bool(avoidance and avoidance > 0)
    if has_saving and has_avoidance:
        return "both"
    if has_saving:
        return "cost_saving"
    if has_avoidance:
        return "cost_avoidance"
    return "kpi_only"


def prefilled_charter(idea: Idea, *, leader: User | None, kpi_hint: str) -> ProjectCharter:
    """A draft charter that reuses everything the approved idea already told us."""
    return ProjectCharter(
        tenant_id=idea.tenant_id,
        idea_id=idea.id,
        sponsor="",
        leader=leader.display_name if leader else "",
        leader_user_id=leader.id if leader else None,
        department_id=idea.department_id,
        site_id=idea.site_id,
        target_completion_date=idea.target_completion_date,
        impact_areas=list(idea.impacts or []),
        benefit_type=benefit_type_for(idea.estimated_annual_saving, idea.cost_avoidance),
        kpi_name=kpi_hint[:160],
        budget_approved=idea.investment_required,
        team_members=[],
        team_membership_ids=[],
        action_items=[],
        monthly_tracking=[],
    )


async def _subcategory_kpi(
    session: AsyncSession, tenant_id: uuid.UUID, subcategory_id: uuid.UUID | None
) -> str:
    if subcategory_id is None:
        return ""
    guidance = await session.scalar(
        select(ConfigurationItem.guidance).where(
            ConfigurationItem.tenant_id == tenant_id, ConfigurationItem.id == subcategory_id
        )
    )
    return str((guidance or {}).get("kpi") or "")


async def _active_member_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> User | None:
    return await session.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            User.id == user_id,
            Membership.tenant_id == tenant_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )


async def get_charter_workspace(
    tenant_id: uuid.UUID, user_id: uuid.UUID, project_id: uuid.UUID, session: AsyncSession
) -> CharterWorkspaceRecord:
    """Everything the charter page needs: the charter, the approved idea it builds on, and rights."""
    site = aliased(ConfigurationItem)
    department = aliased(ConfigurationItem)
    category = aliased(ConfigurationItem)
    subcategory = aliased(ConfigurationItem)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        row = (
            await session.execute(
                select(
                    Project,
                    Idea,
                    ProjectCharter,
                    User.display_name,
                    site.name,
                    department.name,
                    category.name,
                    subcategory.name,
                    subcategory.guidance,
                )
                .join(Idea, Idea.id == Project.idea_id)
                .join(ProjectCharter, ProjectCharter.idea_id == Idea.id)
                .join(User, User.id == Idea.submitter_user_id)
                .outerjoin(site, site.id == Idea.site_id)
                .outerjoin(department, department.id == Idea.department_id)
                .outerjoin(category, category.id == Idea.category_id)
                .outerjoin(subcategory, subcategory.id == Idea.subcategory_id)
                .where(Project.tenant_id == tenant_id, Project.id == project_id)
            )
        ).one_or_none()
        if row is None:
            raise IdeaNotFoundError
        (
            project,
            idea,
            charter,
            submitter_name,
            site_name,
            department_name,
            category_name,
            subcategory_name,
            guidance,
        ) = row
        return CharterWorkspaceRecord(
            project_id=project.id,
            project_reference=project.reference,
            project_status=project.status,
            can_edit=idea.submitter_user_id == user_id and charter.submitted_at is None,
            charter=_charter_record(charter),
            idea=CharterIdeaContext(
                id=idea.id,
                reference=idea.reference,
                title=idea.title,
                idea_type=idea.idea_type,
                project_subtype=idea.project_subtype,
                submitter_name=submitter_name,
                submitter_user_id=idea.submitter_user_id,
                site_id=idea.site_id,
                site=site_name,
                department_id=idea.department_id,
                department=department_name,
                category=category_name,
                subcategory=subcategory_name,
                impacts=list(idea.impacts or []),
                current_state=idea.current_state,
                baseline_uom=idea.baseline_uom,
                target_state=idea.target_state,
                target_uom=idea.target_uom,
                target_completion_date=idea.target_completion_date,
                estimated_annual_saving=idea.estimated_annual_saving,
                cost_avoidance=idea.cost_avoidance,
                investment_required=idea.investment_required,
                kpi_hint=str((guidance or {}).get("kpi") or ""),
                suggested_benefit_type=benefit_type_for(
                    idea.estimated_annual_saving, idea.cost_avoidance
                ),
            ),
        )


async def _has_active_catalog_items(session: AsyncSession, tenant_id: uuid.UUID, kind: str) -> bool:
    count = await session.scalar(
        select(func.count(ConfigurationItem.id)).where(
            ConfigurationItem.tenant_id == tenant_id,
            ConfigurationItem.kind == kind,
            ConfigurationItem.is_active.is_(True),
        )
    )
    return bool(count)


def milestone_plan_problems(
    plan: list[CharterMilestone], start: date | None, target: date | None, benefit_type: str
) -> list[str]:
    """Plain-language reasons a charter's milestone plan can't be submitted yet."""
    if not plan:
        return ["Add at least one milestone."]
    problems: list[str] = []
    if any(not milestone.title.strip() for milestone in plan):
        problems.append("Every milestone needs a title.")
    if any(milestone.due_date is None for milestone in plan):
        problems.append("Every milestone needs a due date.")
    outside = [
        milestone.title or "Untitled"
        for milestone in plan
        if milestone.due_date
        and ((start and milestone.due_date < start) or (target and milestone.due_date > target))
    ]
    if outside:
        problems.append(f"Due dates must fall within the charter dates ({', '.join(outside)}).")
    total = sum((milestone.weight for milestone in plan), Decimal(0))
    if total != 100:
        problems.append(f"Weights must total 100% (now {total.normalize():f}%).")
    starts = sum(1 for milestone in plan if milestone.benefits_start)
    if benefit_type != "kpi_only" and starts != 1:
        problems.append("Mark the one milestone after which benefits start.")
    elif starts > 1:
        problems.append("Only one milestone can mark when benefits start.")
    return problems
