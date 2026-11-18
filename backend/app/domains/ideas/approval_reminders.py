"""Overdue approval reminders and escalation.

Run by the scheduled job. A pending task past its due time gets a reminder, then one more
every ``REMINDER_INTERVAL`` up to ``MAX_REMINDERS``. The last reminder also escalates to the
approver's reporting manager from the HR directory, or to the Workspace Admins when no
manager is known. Each task's counters make the job safe to run as often as you like.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.directory.models import DirectoryEmployee
from app.domains.ideas.approval_notifications import (
    APPROVAL_PREFERENCE,
    _context,
    _send,
    wants_email,
)
from app.domains.ideas.approval_routing import directory_record_for_user
from app.domains.ideas.models import Idea, IdeaApprovalStage, IdeaStatus
from app.domains.identity.access import ADMIN_ROLE_KEYS
from app.domains.identity.models import Membership, MembershipStatus, Role, User, membership_roles

REMINDER_INTERVAL = timedelta(hours=24)
MAX_REMINDERS = 3
MAX_ADMIN_ESCALATIONS = 5


@dataclass
class ReminderSummary:
    reminded: int = 0
    escalated: int = 0


def _overdue_by(due_at: datetime, now: datetime) -> str:
    hours = int((now - due_at).total_seconds() // 3600)
    if hours < 24:
        return f"{max(hours, 1)} hour{'s' if hours != 1 else ''}"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''}"


async def _escalation_contacts(
    session: AsyncSession, tenant_id: uuid.UUID, approver_id: uuid.UUID
) -> tuple[list[User], str]:
    """The approver's reporting manager, or the Workspace Admins as a fallback."""
    record = await directory_record_for_user(session, tenant_id, approver_id)
    if record is not None and record.manager_employee_id:
        manager = await session.scalar(
            select(DirectoryEmployee).where(
                DirectoryEmployee.tenant_id == tenant_id,
                DirectoryEmployee.employee_id == record.manager_employee_id,
                DirectoryEmployee.status != "left",
                DirectoryEmployee.user_id.is_not(None),
            )
        )
        if manager is not None and manager.user_id != approver_id:
            user = await session.scalar(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    User.id == manager.user_id,
                    Membership.tenant_id == tenant_id,
                    # Invited by the HR sync but not signed in yet still has a working email.
                    Membership.status.in_((MembershipStatus.ACTIVE, MembershipStatus.INVITED)),
                )
            )
            if user is not None:
                return [user], "reporting manager"
    admins = (
        await session.scalars(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .join(membership_roles, membership_roles.c.membership_id == Membership.id)
            .join(Role, Role.id == membership_roles.c.role_id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.status == MembershipStatus.ACTIVE,
                Role.tenant_id == tenant_id,
                Role.key.in_(ADMIN_ROLE_KEYS),
                User.id != approver_id,
            )
            .order_by(User.display_name)
            .limit(MAX_ADMIN_ESCALATIONS)
        )
    ).all()
    return list(admins), "Workspace Admin"


async def send_overdue_reminders(
    tenant_id: uuid.UUID,
    settings: Settings,
    session: AsyncSession,
    now: datetime | None = None,
) -> ReminderSummary:
    now = now or datetime.now(UTC)
    summary = ReminderSummary()
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        rows = (
            await session.execute(
                select(IdeaApprovalStage, Idea)
                .join(Idea, Idea.id == IdeaApprovalStage.idea_id)
                .where(
                    IdeaApprovalStage.tenant_id == tenant_id,
                    IdeaApprovalStage.status == "pending",
                    IdeaApprovalStage.due_at.is_not(None),
                    IdeaApprovalStage.due_at < now,
                    IdeaApprovalStage.assignee_user_id.is_not(None),
                    IdeaApprovalStage.reminder_count < MAX_REMINDERS,
                    or_(
                        IdeaApprovalStage.last_reminded_at.is_(None),
                        IdeaApprovalStage.last_reminded_at <= now - REMINDER_INTERVAL,
                    ),
                    Idea.status == IdeaStatus.SUBMITTED,
                )
                .order_by(IdeaApprovalStage.due_at)
                .with_for_update(of=IdeaApprovalStage, skip_locked=True)
            )
        ).all()
        for task, idea in rows:
            task.reminder_count += 1
            task.last_reminded_at = now
            approver = await session.get(User, task.assignee_user_id)
            if approver is None:
                continue
            _, _, data = await _context(session, idea, settings)
            final = task.reminder_count >= MAX_REMINDERS
            overdue = _overdue_by(task.due_at, now)  # type: ignore[arg-type]
            step = {
                **data,
                "stage_name": task.stage_name,
                "overdue_by": overdue,
                "due": f"{task.due_at:%d %b %Y, %H:%M} UTC",
                "reminder_number": str(task.reminder_count),
                "final_reminder": "yes" if final else "",
                "action_label": "Review and decide",
            }
            if wants_email(approver, APPROVAL_PREFERENCE):
                _send(
                    session,
                    settings,
                    idea,
                    recipient=approver,
                    template_key="approval_overdue",
                    subject=f"Overdue by {overdue}: approval for {idea.reference}",
                    data=step,
                )
                summary.reminded += 1
            if not final:
                continue
            contacts, relation = await _escalation_contacts(session, tenant_id, approver.id)
            for contact in contacts:
                _send(
                    session,
                    settings,
                    idea,
                    recipient=contact,
                    template_key="approval_escalation",
                    subject=f"Stuck approval: {idea.reference} is waiting on {approver.display_name}",
                    data={
                        **step,
                        "approver_name": approver.display_name,
                        "relation": relation,
                        "action_label": "View the idea",
                    },
                )
                summary.escalated += 1
        await session.flush()
    return summary
