"""Approval and review emails.

``dispatch_approval_notifications`` is safe to call after any change to an idea's approval
tasks (submission, a decision, an HR re-route): bookkeeping columns make every notice go
out exactly once. Personal preferences are honoured for routine notices; security notices
(role changes) live in the tenants domain and are always sent.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.urls import preferences_link, tenant_frontend_url
from app.domains.communications.controllers import enqueue_email
from app.domains.communications.schemas import EmailMessage
from app.domains.configuration.models import WorkflowVersion
from app.domains.directory.models import DirectoryEmployee
from app.domains.ideas.approval_routing import (
    Approver,
    _group_members,
    _routable_approvers,
    directory_record_for_user,
)
from app.domains.ideas.models import Idea, IdeaApprovalStage, IdeaStepConsultation
from app.domains.identity.models import Membership, User
from app.domains.tenants.models import Tenant

APPROVAL_PREFERENCE = "email_approval_updates"
IDEA_PREFERENCE = "email_idea_updates"
MAX_CONSULTEES = 200


def wants_email(user: User | None, preference: str) -> bool:
    if user is None:
        return False
    return bool((user.profile_settings or {}).get(preference, True))


def _first_name(name: str) -> str:
    return name.split(" ")[0] if name else "there"


def _money(value: Decimal | None) -> str:
    return f"₹{value:,.0f}" if value is not None else "Not estimated"


async def _context(
    session: AsyncSession, idea: Idea, settings: Settings
) -> tuple[Tenant, User | None, dict[str, str]]:
    tenant = await session.get(Tenant, idea.tenant_id)
    assert tenant is not None
    submitter = await session.get(User, idea.submitter_user_id)
    return (
        tenant,
        submitter,
        {
            "tenant_name": tenant.name,
            "idea_reference": idea.reference,
            "idea_title": idea.title,
            "submitter_name": submitter.display_name if submitter else "A colleague",
            "problem_statement": idea.problem_statement or "Not provided",
            "estimated_saving": _money(idea.estimated_annual_saving),
            "action_url": tenant_frontend_url(
                settings, tenant.slug, f"/ideas/{idea.id}", query={"section": "approval"}
            ),
            **preferences_link(settings, tenant.slug),
        },
    )


def _send(
    session: AsyncSession,
    settings: Settings,
    idea: Idea,
    *,
    recipient: User,
    template_key: str,
    subject: str,
    data: dict[str, str],
) -> None:
    enqueue_email(
        session,
        EmailMessage(
            tenant_id=idea.tenant_id,
            recipient=recipient.email,
            template_key=template_key,
            subject=subject,
            template_data={**data, "recipient_name": recipient.display_name},
        ),
        settings,
    )


async def consultation_audience(
    session: AsyncSession,
    idea: Idea,
    stage: dict[str, object],
    exclude_user_ids: set[uuid.UUID],
) -> list[Approver]:
    """Everyone asked for comments when a step starts, minus approvers and the submitter."""
    kind = str(stage.get("notify_kind") or "none")
    people: list[Approver] = []
    if kind == "group":
        _, people = await _group_members(
            session, idea.tenant_id, stage.get("notify_group_id"), lock=False
        )
    elif kind in ("hods_same_location", "hods_all"):
        hod_ids = select(DirectoryEmployee.hod_employee_id).where(
            DirectoryEmployee.tenant_id == idea.tenant_id,
            DirectoryEmployee.status == "active",
            DirectoryEmployee.hod_employee_id.is_not(None),
        )
        statement = select(DirectoryEmployee.user_id).where(
            DirectoryEmployee.tenant_id == idea.tenant_id,
            DirectoryEmployee.status != "left",
            DirectoryEmployee.user_id.is_not(None),
            DirectoryEmployee.employee_id.in_(hod_ids),
        )
        if kind == "hods_same_location":
            subject = await directory_record_for_user(
                session, idea.tenant_id, idea.submitter_user_id
            )
            if subject is None or not subject.location:
                return []
            statement = statement.where(DirectoryEmployee.location == subject.location)
        user_ids = [user_id for user_id in (await session.scalars(statement)).all() if user_id]
        membership_ids = list(
            (
                await session.scalars(
                    select(Membership.id).where(
                        Membership.tenant_id == idea.tenant_id, Membership.user_id.in_(user_ids)
                    )
                )
            ).all()
        )
        people = await _routable_approvers(session, idea.tenant_id, membership_ids)
    excluded = exclude_user_ids | {idea.submitter_user_id}
    seen: set[uuid.UUID] = set()
    audience = []
    for person in people:
        if person.user_id in excluded or person.user_id in seen:
            continue
        seen.add(person.user_id)
        audience.append(person)
    return audience[:MAX_CONSULTEES]


async def dispatch_approval_notifications(
    session: AsyncSession, idea: Idea, settings: Settings
) -> None:
    now = datetime.now(UTC)
    tasks = list(
        (
            await session.scalars(
                select(IdeaApprovalStage)
                .where(
                    IdeaApprovalStage.tenant_id == idea.tenant_id,
                    IdeaApprovalStage.idea_id == idea.id,
                    (
                        (IdeaApprovalStage.status == "pending")
                        & IdeaApprovalStage.notified_at.is_(None)
                    )
                    | (
                        (IdeaApprovalStage.status == "reassigned")
                        & IdeaApprovalStage.closure_notified_at.is_(None)
                    ),
                )
                .order_by(IdeaApprovalStage.stage_order, IdeaApprovalStage.sequence)
                .with_for_update()
            )
        ).all()
    )
    if not tasks:
        return
    _, _, data = await _context(session, idea, settings)
    version = (
        await session.get(WorkflowVersion, idea.workflow_version_id)
        if idea.workflow_version_id
        else None
    )
    consulted_steps: set[tuple[int, int]] = set()
    for task in tasks:
        user = await session.get(User, task.assignee_user_id) if task.assignee_user_id else None
        step = {**data, "stage_name": task.stage_name}
        if task.status == "reassigned":
            task.closure_notified_at = now
            if wants_email(user, APPROVAL_PREFERENCE):
                _send(
                    session,
                    settings,
                    idea,
                    recipient=user,  # type: ignore[arg-type]
                    template_key="approval_withdrawn",
                    subject=f"No longer needed: approval for {idea.reference}",
                    data={**step, "reason": task.resolution_note or "The approval route changed."},
                )
            continue
        task.notified_at = now
        if wants_email(user, APPROVAL_PREFERENCE):
            _send(
                session,
                settings,
                idea,
                recipient=user,  # type: ignore[arg-type]
                template_key="approval_request",
                subject=f"Approval needed: {idea.reference} {idea.title}",
                data={
                    **step,
                    "due": f"{task.due_at:%d %b %Y, %H:%M} UTC" if task.due_at else "No deadline",
                    "action_label": "Review and decide",
                },
            )
        consulted_steps.add((task.round_number, task.stage_order))

    for round_number, order in sorted(consulted_steps):
        if version is None or order > len(version.stages):
            continue
        stage = version.stages[order - 1]
        if (stage.get("notify_kind") or "none") == "none":
            continue
        if await session.scalar(
            select(IdeaStepConsultation.id).where(
                IdeaStepConsultation.tenant_id == idea.tenant_id,
                IdeaStepConsultation.idea_id == idea.id,
                IdeaStepConsultation.round_number == round_number,
                IdeaStepConsultation.stage_order == order,
            )
        ):
            continue
        approvers = {
            task.assignee_user_id
            for task in (
                await session.scalars(
                    select(IdeaApprovalStage).where(
                        IdeaApprovalStage.tenant_id == idea.tenant_id,
                        IdeaApprovalStage.idea_id == idea.id,
                        IdeaApprovalStage.round_number == round_number,
                        IdeaApprovalStage.stage_order == order,
                    )
                )
            ).all()
            if task.assignee_user_id
        }
        audience = await consultation_audience(session, idea, stage, approvers)
        stage_name = str(stage.get("name", f"Step {order}"))
        session.add(
            IdeaStepConsultation(
                tenant_id=idea.tenant_id,
                idea_id=idea.id,
                round_number=round_number,
                stage_order=order,
                stage_name=stage_name,
                user_ids=[str(person.user_id) for person in audience],
            )
        )
        approver_names = ", ".join(
            user.display_name
            for user in (await session.scalars(select(User).where(User.id.in_(approvers)))).all()
        )
        for person in audience:
            user = await session.get(User, person.user_id)
            if not wants_email(user, APPROVAL_PREFERENCE):
                continue
            _send(
                session,
                settings,
                idea,
                recipient=user,  # type: ignore[arg-type]
                template_key="comment_request",
                subject=f"Your view is requested: {idea.reference} {idea.title}",
                data={
                    **data,
                    "stage_name": stage_name,
                    "approver_names": approver_names or "the approver",
                    "action_label": "Read and comment",
                },
            )
    await session.flush()


async def notify_submitter_of_decision(
    session: AsyncSession,
    idea: Idea,
    task: IdeaApprovalStage,
    decision: str,
    settings: Settings,
) -> None:
    """Corrections and rejections; full approval has its own charter email."""
    if decision not in ("needs_correction", "reject"):
        return
    _, submitter, data = await _context(session, idea, settings)
    if not wants_email(submitter, IDEA_PREFERENCE):
        return
    tenant = await session.get(Tenant, idea.tenant_id)
    correction = decision == "needs_correction"
    _send(
        session,
        settings,
        idea,
        recipient=submitter,  # type: ignore[arg-type]
        template_key="idea_needs_correction" if correction else "idea_rejected",
        subject=(
            f"Changes requested: {idea.reference} {idea.title}"
            if correction
            else f"Not approved: {idea.reference} {idea.title}"
        ),
        data={
            **data,
            "stage_name": task.stage_name,
            "approver_name": task.assignee_name or "The approver",
            "comment": task.decision_comment or "No comment was added.",
            "action_url": tenant_frontend_url(
                settings,
                tenant.slug if tenant else "",
                "/ideas/new/v2" if correction else f"/ideas/{idea.id}",
                query={"resume": str(idea.id)} if correction else None,
            ),
            "action_label": "Correct your idea" if correction else "View your idea",
        },
    )
