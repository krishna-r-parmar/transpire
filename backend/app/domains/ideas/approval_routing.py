"""Approval routing: who approves each workflow step, and how steps advance.

Workflow steps are resolved *when they become active*, not at submission, so routing always
uses the latest HR directory and approver groups. Placeholder rows are still written at
submission so the idea's journey can be shown in advance; they are re-resolved on activation.

One ``IdeaApprovalStage`` row is one approver's task. Rows sharing ``stage_order`` form one
step. ``completion`` is ``any`` (first approval closes the step) or ``all``; ``sequence``
orders approvers in an "all in sequence" step and is 0 everywhere else.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.configuration.models import ApproverGroup, WorkflowVersion
from app.domains.directory.models import DirectoryEmployee
from app.domains.ideas.models import Idea, IdeaApprovalStage
from app.domains.identity.access import ADMIN_ROLE_KEYS
from app.domains.identity.models import Membership, MembershipStatus, Role, User, membership_roles
from app.domains.identity.queries import contributing_membership

ROUTABLE_STATUSES = (MembershipStatus.ACTIVE, MembershipStatus.INVITED)
OPEN_STATUSES = ("pending", "waiting")

RELATIONSHIP_LABELS = {"reporting_manager": "Reporting manager", "hod": "Head of department"}
MODE_LABELS = {
    "any": "Any one approves",
    "round_robin": "Round robin",
    "all_sequential": "All, in sequence",
    "all_parallel": "All, in parallel",
}


@dataclass(frozen=True)
class Approver:
    membership_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: str


@dataclass
class ResolvedStep:
    approvers: list[Approver] = field(default_factory=list)
    completion: str = "all"
    sequential: bool = False
    note: str = ""

    @property
    def skipped(self) -> bool:
        return not self.approvers


async def _routable_approvers(
    session: AsyncSession, tenant_id: uuid.UUID, membership_ids: list[uuid.UUID]
) -> list[Approver]:
    """Members who can approve (active or invited, not Viewers), in the given order."""
    if not membership_ids:
        return []
    rows = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.id.in_(membership_ids),
                Membership.status.in_(ROUTABLE_STATUSES),
                contributing_membership(Membership.id, tenant_id),
            )
        )
    ).all()
    found = {
        membership.id: Approver(membership.id, user.id, user.display_name, user.email)
        for membership, user in rows
    }
    return [found[member_id] for member_id in membership_ids if member_id in found]


async def _membership_for_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID | None:
    return await session.scalar(
        select(Membership.id).where(
            Membership.tenant_id == tenant_id, Membership.user_id == user_id
        )
    )


async def directory_record_for_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> DirectoryEmployee | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    return await session.scalar(
        select(DirectoryEmployee)
        .where(
            DirectoryEmployee.tenant_id == tenant_id,
            DirectoryEmployee.status != "left",
            (DirectoryEmployee.user_id == user_id)
            | (DirectoryEmployee.email == user.email.casefold()),
        )
        .order_by((DirectoryEmployee.user_id == user_id).desc())
        .limit(1)
    )


async def _resolve_dynamic(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    relationship: str,
    subject: DirectoryEmployee | None,
) -> tuple[list[Approver], str]:
    label = RELATIONSHIP_LABELS.get(relationship, relationship)
    if subject is None:
        return [], f"{label}: the submitter is not in the HR directory."
    target_id = (
        subject.manager_employee_id
        if relationship == "reporting_manager"
        else subject.hod_employee_id
    )
    if not target_id:
        return [], f"{label}: none recorded for {subject.display_name} in the HR file."
    target = await session.scalar(
        select(DirectoryEmployee).where(
            DirectoryEmployee.tenant_id == tenant_id, DirectoryEmployee.employee_id == target_id
        )
    )
    if target is None:
        return [], f"{label}: HR ID {target_id} is not in the HR file."
    if target.status == "left":
        return [], f"{label}: {target.display_name} has left the organisation."
    if target.user_id is None:
        return [], f"{label}: {target.display_name} has no TRANSPIRE account yet."
    membership_id = await _membership_for_user(session, tenant_id, target.user_id)
    approvers = await _routable_approvers(
        session, tenant_id, [membership_id] if membership_id else []
    )
    if not approvers:
        return [], f"{label}: {target.display_name} cannot approve in this workspace."
    return approvers, f"{label} of {subject.display_name}, from the HR directory."


async def _group_members(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: str | None, *, lock: bool
) -> tuple[ApproverGroup | None, list[Approver]]:
    if not group_id:
        return None, []
    statement = select(ApproverGroup).where(
        ApproverGroup.tenant_id == tenant_id, ApproverGroup.id == uuid.UUID(str(group_id))
    )
    group = await session.scalar(statement.with_for_update() if lock else statement)
    if group is None or not group.is_active:
        return group, []
    member_ids = [uuid.UUID(str(value)) for value in group.member_membership_ids]
    return group, await _routable_approvers(session, tenant_id, member_ids)


async def _workspace_admin(
    session: AsyncSession, tenant_id: uuid.UUID, exclude_user_id: uuid.UUID
) -> list[Approver]:
    row = (
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
                User.id != exclude_user_id,
            )
            .order_by(User.display_name)
            .limit(1)
        )
    ).first()
    return [Approver(row[0].id, row[1].id, row[1].display_name, row[1].email)] if row else []


async def resolve_step(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    stage: dict[str, object],
    submitter_user_id: uuid.UUID,
    previous_approver_ids: set[uuid.UUID],
    *,
    activate: bool,
    subject: DirectoryEmployee | None = None,
    subject_loaded: bool = False,
) -> ResolvedStep:
    """Work out who approves one step for one submitter.

    ``activate`` advances round-robin rotation; placeholders and previews leave it alone.
    """
    source = str(
        stage.get("source") or ("person" if stage.get("assignee_membership_id") else "group")
    )
    mode = str(stage.get("mode") or "any")
    notes: list[str] = []
    approvers: list[Approver] = []
    completion, sequential = "all", False

    if source == "dynamic":
        if not subject_loaded:
            subject = await directory_record_for_user(session, tenant_id, submitter_user_id)
        approvers, note = await _resolve_dynamic(
            session, tenant_id, str(stage.get("relationship")), subject
        )
        notes.append(note)
    elif source == "person":
        member_id = stage.get("assignee_membership_id")
        approvers = await _routable_approvers(
            session, tenant_id, [uuid.UUID(str(member_id))] if member_id else []
        )
        if not approvers:
            notes.append("The assigned person can no longer approve.")
    else:
        group, members = await _group_members(
            session, tenant_id, stage.get("group_id"), lock=activate and mode == "round_robin"
        )
        members = [member for member in members if member.user_id != submitter_user_id]
        group_name = group.name if group else "The approver group"
        if not members:
            notes.append(f"{group_name} has no one available to approve.")
        elif mode == "round_robin":
            approvers = [members[(group.round_robin_cursor if group else 0) % len(members)]]
            if activate and group is not None:
                group.round_robin_cursor += 1
            notes.append(f"{group_name}, round robin.")
        else:
            approvers = members
            completion = "any" if mode == "any" else "all"
            sequential = mode == "all_sequential"
            notes.append(f"{group_name}, {MODE_LABELS.get(mode, mode).lower()}.")

    if any(approver.user_id == submitter_user_id for approver in approvers):
        approvers = [approver for approver in approvers if approver.user_id != submitter_user_id]
        notes.append("The submitter cannot approve their own idea.")

    if not approvers:
        rule = str(stage.get("on_unresolved") or "skip")
        if rule == "fallback_group":
            group, members = await _group_members(
                session, tenant_id, stage.get("fallback_group_id"), lock=False
            )
            approvers = [member for member in members if member.user_id != submitter_user_id]
            completion, sequential = "any", False
            if approvers and group is not None:
                notes.append(f"Sent to fallback group {group.name}.")
        elif rule == "fallback_admin":
            approvers = await _workspace_admin(session, tenant_id, submitter_user_id)
            completion, sequential = "any", False
            if approvers:
                notes.append("Sent to a Workspace Admin.")
        if not approvers:
            notes.append("Step skipped: no approver available.")
            return ResolvedStep(note=" ".join(notes))

    if (
        stage.get("skip_if_same_as_previous", True)
        and previous_approver_ids
        and {approver.user_id for approver in approvers} <= previous_approver_ids
    ):
        return ResolvedStep(note="Step skipped: same approver as the previous step.")

    return ResolvedStep(
        approvers=approvers, completion=completion, sequential=sequential, note=" ".join(notes)
    )


def _rows_for(
    idea: Idea,
    stage: dict[str, object],
    order: int,
    round_number: int,
    resolved: ResolvedStep,
    *,
    status: str,
) -> list[IdeaApprovalStage]:
    common = {
        "tenant_id": idea.tenant_id,
        "idea_id": idea.id,
        "round_number": round_number,
        "stage_order": order,
        "stage_key": str(stage.get("key", f"stage_{order}")),
        "stage_name": str(stage.get("name", f"Approval stage {order}")),
        "sla_hours": int(stage.get("sla_hours", 48)),
        "resolution_note": resolved.note or None,
    }
    if resolved.skipped:
        return [IdeaApprovalStage(**common, status="skipped", completion="all", sequence=0)]
    return [
        IdeaApprovalStage(
            **common,
            assignee_membership_id=approver.membership_id,
            assignee_user_id=approver.user_id,
            assignee_name=approver.name,
            assignee_email=approver.email,
            completion=resolved.completion,
            sequence=position + 1 if resolved.sequential else 0,
            status=status,
        )
        for position, approver in enumerate(resolved.approvers)
    ]


async def instantiate_round(
    session: AsyncSession,
    idea: Idea,
    version: WorkflowVersion,
    round_number: int,
    now: datetime,
) -> bool:
    """Write the journey for a new approval round and activate its first step.

    Returns False when every step was skipped (nothing to approve).
    """
    subject = await directory_record_for_user(session, idea.tenant_id, idea.submitter_user_id)
    previous: set[uuid.UUID] = set()
    for index, stage in enumerate(version.stages):
        resolved = await resolve_step(
            session,
            idea.tenant_id,
            stage,
            idea.submitter_user_id,
            previous,
            activate=False,
            subject=subject,
            subject_loaded=True,
        )
        session.add_all(_rows_for(idea, stage, index + 1, round_number, resolved, status="waiting"))
        if not resolved.skipped:
            previous = {approver.user_id for approver in resolved.approvers}
    await session.flush()
    return await activate_next_step(session, idea, version, round_number, after_order=0, now=now)


async def _approved_user_ids(
    session: AsyncSession, idea: Idea, round_number: int, before_order: int
) -> set[uuid.UUID]:
    rows = (
        await session.execute(
            select(IdeaApprovalStage.stage_order, IdeaApprovalStage.assignee_user_id).where(
                IdeaApprovalStage.tenant_id == idea.tenant_id,
                IdeaApprovalStage.idea_id == idea.id,
                IdeaApprovalStage.round_number == round_number,
                IdeaApprovalStage.stage_order < before_order,
                IdeaApprovalStage.status == "approve",
            )
        )
    ).all()
    if not rows:
        return set()
    last = max(order for order, _ in rows)
    return {user_id for order, user_id in rows if order == last and user_id}


async def activate_next_step(
    session: AsyncSession,
    idea: Idea,
    version: WorkflowVersion,
    round_number: int,
    *,
    after_order: int,
    now: datetime,
) -> bool:
    """Resolve and open the next step after ``after_order``. False when none is left."""
    subject = await directory_record_for_user(session, idea.tenant_id, idea.submitter_user_id)
    for index in range(after_order, len(version.stages)):
        stage = version.stages[index]
        order = index + 1
        await session.execute(
            delete(IdeaApprovalStage).where(
                IdeaApprovalStage.tenant_id == idea.tenant_id,
                IdeaApprovalStage.idea_id == idea.id,
                IdeaApprovalStage.round_number == round_number,
                IdeaApprovalStage.stage_order == order,
                IdeaApprovalStage.status.in_(("waiting", "skipped")),
            )
        )
        resolved = await resolve_step(
            session,
            idea.tenant_id,
            stage,
            idea.submitter_user_id,
            await _approved_user_ids(session, idea, round_number, order),
            activate=True,
            subject=subject,
            subject_loaded=True,
        )
        rows = _rows_for(idea, stage, order, round_number, resolved, status="waiting")
        if resolved.skipped:
            session.add_all(rows)
            continue
        first_sequence = min(row.sequence for row in rows)
        for row in rows:
            if row.sequence == first_sequence:
                row.status = "pending"
                row.due_at = now + timedelta(hours=row.sla_hours)
        session.add_all(rows)
        await session.flush()
        return True
    await session.flush()
    return False


async def complete_task(session: AsyncSession, task: IdeaApprovalStage, now: datetime) -> bool:
    """Record an approval on one task. True when its whole step is now complete."""
    siblings = list(
        (
            await session.scalars(
                select(IdeaApprovalStage)
                .where(
                    IdeaApprovalStage.tenant_id == task.tenant_id,
                    IdeaApprovalStage.idea_id == task.idea_id,
                    IdeaApprovalStage.round_number == task.round_number,
                    IdeaApprovalStage.stage_order == task.stage_order,
                    IdeaApprovalStage.id != task.id,
                    IdeaApprovalStage.status.in_(OPEN_STATUSES),
                )
                .order_by(IdeaApprovalStage.sequence)
                .with_for_update()
            )
        ).all()
    )
    if task.completion == "any":
        for sibling in siblings:
            sibling.status = "superseded"
            sibling.resolution_note = f"Closed: {task.assignee_name} approved for the group."
        return True
    waiting = [sibling for sibling in siblings if sibling.status == "waiting"]
    if any(sibling.status == "pending" for sibling in siblings):
        return False
    if waiting:
        next_sequence = min(sibling.sequence for sibling in waiting)
        for sibling in waiting:
            if sibling.sequence == next_sequence:
                sibling.status = "pending"
                sibling.due_at = now + timedelta(hours=sibling.sla_hours)
        return False
    return True


async def close_round(session: AsyncSession, task: IdeaApprovalStage) -> None:
    """A rejection or correction request ends the round: cancel every open task."""
    for open_task in (
        await session.scalars(
            select(IdeaApprovalStage).where(
                IdeaApprovalStage.tenant_id == task.tenant_id,
                IdeaApprovalStage.idea_id == task.idea_id,
                IdeaApprovalStage.round_number == task.round_number,
                IdeaApprovalStage.id != task.id,
                IdeaApprovalStage.status.in_(OPEN_STATUSES),
            )
        )
    ).all():
        open_task.status = "cancelled"


@dataclass
class RerouteResult:
    notes: list[str] = field(default_factory=list)
    # The active step resolved to nobody and was skipped: the caller must open the next
    # step, or complete the approval when none is left.
    step_skipped_at: int | None = None


async def reroute_pending(
    session: AsyncSession, idea: Idea, version: WorkflowVersion, now: datetime
) -> RerouteResult:
    """Re-resolve the active step of one idea after HR or group changes.

    Pending tasks whose approver should change are closed as "reassigned" and the new
    approvers get fresh pending tasks. Decisions already made are never touched. Returns
    human-readable notes for the run report; no notes when nothing changed.
    """
    pending = list(
        (
            await session.scalars(
                select(IdeaApprovalStage)
                .where(
                    IdeaApprovalStage.tenant_id == idea.tenant_id,
                    IdeaApprovalStage.idea_id == idea.id,
                    IdeaApprovalStage.status == "pending",
                )
                .with_for_update()
            )
        ).all()
    )
    if not pending:
        return RerouteResult()
    order, round_number = pending[0].stage_order, pending[0].round_number
    if order > len(version.stages):
        return RerouteResult()
    stage = version.stages[order - 1]
    if any(
        task.status == "approve"
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
    ):
        # Part of this step is already decided; re-routing the rest would mix approver sets.
        current_ids = {task.assignee_membership_id for task in pending}
        still_routable = {
            approver.membership_id
            for approver in await _routable_approvers(
                session, idea.tenant_id, [member for member in current_ids if member]
            )
        }
        if current_ids <= still_routable:
            return RerouteResult()
    current = {task.assignee_user_id for task in pending}
    available = await _routable_approvers(
        session,
        idea.tenant_id,
        [task.assignee_membership_id for task in pending if task.assignee_membership_id],
    )
    source = str(stage.get("source") or "group")
    if source != "dynamic" and len(available) == len(pending):
        return RerouteResult()  # Group and person steps move only when someone cannot approve.
    resolved = await resolve_step(
        session,
        idea.tenant_id,
        stage,
        idea.submitter_user_id,
        await _approved_user_ids(session, idea, round_number, order),
        activate=True,
    )
    if not resolved.skipped and {approver.user_id for approver in resolved.approvers} == current:
        return RerouteResult()
    for task in pending:
        task.status = "reassigned"
        task.resolution_note = f"Reassigned {now:%d %b %Y}: {resolved.note}"
    await session.execute(
        delete(IdeaApprovalStage).where(
            IdeaApprovalStage.tenant_id == idea.tenant_id,
            IdeaApprovalStage.idea_id == idea.id,
            IdeaApprovalStage.round_number == round_number,
            IdeaApprovalStage.stage_order == order,
            IdeaApprovalStage.status == "waiting",
        )
    )
    if resolved.skipped:
        session.add_all(_rows_for(idea, stage, order, round_number, resolved, status="skipped"))
        await session.flush()
        return RerouteResult(
            notes=[f"{idea.reference}: {stage.get('name')} skipped. {resolved.note}"],
            step_skipped_at=order,
        )
    rows = _rows_for(idea, stage, order, round_number, resolved, status="waiting")
    first_sequence = min(row.sequence for row in rows)
    for row in rows:
        if row.sequence == first_sequence:
            row.status = "pending"
            row.due_at = now + timedelta(hours=row.sla_hours)
    session.add_all(rows)
    await session.flush()
    names = ", ".join(approver.name for approver in resolved.approvers)
    return RerouteResult(notes=[f"{idea.reference}: {stage.get('name')} reassigned to {names}."])


# Stored decisions use the verb ("approve", "reject"), as the approval API always has.
_STEP_STATUS_PRIORITY = (
    "reject",
    "needs_correction",
    "pending",
    "waiting",
    "approve",
    "skipped",
    "cancelled",
)


def step_status(tasks: list[IdeaApprovalStage]) -> str:
    """One status for a step made of several approver tasks."""
    statuses = {task.status for task in tasks if task.status not in ("reassigned", "superseded")}
    if not statuses:
        return "approve"
    for status in _STEP_STATUS_PRIORITY:
        if status in statuses:
            if status in ("pending", "waiting") and "approve" in statuses:
                return "pending"
            return status
    return next(iter(statuses))


def collapse_steps(tasks: list[IdeaApprovalStage]) -> list[tuple[IdeaApprovalStage, str]]:
    """First task of each (round, step) with the step's combined status, in order."""
    grouped: dict[tuple[int, int], list[IdeaApprovalStage]] = {}
    for task in tasks:
        grouped.setdefault((task.round_number, task.stage_order), []).append(task)
    return [(group[0], step_status(group)) for _, group in sorted(grouped.items())]


def approver_label(stage: dict[str, object], group_names: dict[str, str]) -> str | None:
    """Who a step goes to, in words a submitter understands, before it is resolved."""
    source = stage.get("source")
    if source == "dynamic":
        return (
            "Your reporting manager"
            if stage.get("relationship") == "reporting_manager"
            else "Your head of department"
        )
    if source == "group":
        name = group_names.get(str(stage.get("group_id")), "Approver group")
        return f"{name} (approver group)"
    value = stage.get("assignee_name")
    return str(value) if value else None
