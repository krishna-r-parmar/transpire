import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.core.urls import tenant_frontend_url
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
    IdeaStatus,
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
    EditableIdeaRecord,
    HomeIdeaSummary,
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
from app.domains.identity.models import Membership, MembershipStatus, Role, User, membership_roles
from app.domains.projects.controllers import (
    assign_project_team,
    create_project_from_submitted_charter,
)
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
                Role.key == "tenant_admin",
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


async def list_idea_bank(tenant_id: uuid.UUID, session: AsyncSession) -> list[IdeaBankEntry]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        policy = await repository.get_policy(session, tenant_id)
        if policy is None:
            policy = IdeaBankPolicy(tenant_id=tenant_id)
            session.add(policy)
            await session.flush()
        entries = []
        for idea, contributor, category, subcategory, process_area in await repository.list_bank(
            session, tenant_id
        ):
            operational = policy.detail_level in {"operational", "full"}
            full = policy.detail_level == "full"
            entries.append(
                IdeaBankEntry(
                    id=idea.id,
                    reference=idea.reference,
                    title=idea.title,
                    status=idea.status.value,
                    idea_type=idea.idea_type,
                    category=category,
                    submitted_at=idea.submitted_at,
                    contributor=contributor if policy.show_contributor else None,
                    subcategory=subcategory if operational else None,
                    process_area=process_area if operational else None,
                    impacts=idea.impacts if operational else None,
                    current_state=idea.current_state if operational else None,
                    baseline_uom=idea.baseline_uom if operational else None,
                    target_state=idea.target_state if operational else None,
                    target_uom=idea.target_uom if operational else None,
                    problem_statement=idea.problem_statement if full else None,
                    business_case=idea.business_case if full else None,
                    estimated_annual_saving=(
                        idea.estimated_annual_saving if policy.show_financials else None
                    ),
                    cost_avoidance=idea.cost_avoidance if policy.show_financials else None,
                    investment_required=idea.investment_required
                    if policy.show_financials
                    else None,
                    estimated_annual_saving_usd=(
                        _as_usd(idea.estimated_annual_saving, idea.usd_exchange_rate)
                        if policy.show_financials
                        else None
                    ),
                    cost_avoidance_usd=(
                        _as_usd(idea.cost_avoidance, idea.usd_exchange_rate)
                        if policy.show_financials
                        else None
                    ),
                    investment_required_usd=(
                        _as_usd(idea.investment_required, idea.usd_exchange_rate)
                        if policy.show_financials
                        else None
                    ),
                    usd_exchange_rate=idea.usd_exchange_rate if policy.show_financials else None,
                    fx_rate_date=idea.fx_rate_date if policy.show_financials else None,
                )
            )
        return entries


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
            show_contributor=policy.show_contributor,
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
        policy.show_contributor = command.show_contributor
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
        return HomeWorkspaceSummary(
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
        is_assignee = any(stage.assignee_user_id == user_id for stage in stages)
        is_shared = idea.status in {
            IdeaStatus.SUBMITTED,
            IdeaStatus.APPROVED,
            IdeaStatus.CHARTER_IN_PROGRESS,
            IdeaStatus.CHARTER_SUBMITTED,
        }
        if not (is_shared or is_submitter or is_assignee or "tenant_admin" in roles):
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
                charter = ProjectCharter(
                    tenant_id=tenant_id,
                    idea_id=idea.id,
                    department_id=idea.department_id,
                    site_id=idea.site_id,
                    impact_areas=idea.impacts,
                )
                session.add(charter)
                submitter = await session.get(User, idea.submitter_user_id)
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
        payload = command.model_dump()
        payload["team_membership_ids"] = valid_membership_ids
        if selected_members:
            selected_names = [user.display_name for _, user in selected_members]
            payload["team_members"] = list(dict.fromkeys([*selected_names, *command.team_members]))
        for field, value in payload.items():
            setattr(charter, field, value)
        invitations_queued = 0
        invitations_skipped = len(command.team_membership_ids) - len(valid_membership_ids)
        if submit:
            required = {
                "sponsor or facilitator": command.sponsor.strip(),
                "project or team leader": command.leader.strip(),
                "department": command.department_id,
                "site": command.site_id,
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
        elif idea.status == IdeaStatus.APPROVED:
            idea.status = IdeaStatus.CHARTER_IN_PROGRESS
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
