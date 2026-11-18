"""Administrator-initiated reminders asking members to check in (sign in) to TRANSPIRE.

Each reminder is an ``email_deliveries`` outbox row with the ``check_in_reminder``
template, so the outbox is both the send path and the record of when a person was
last reminded. A per-recipient cooldown stops the same person being reminded again
too soon, however many administrators press send.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.core.tenant_resolution import ResolvedTenant
from app.core.urls import preferences_link, tenant_frontend_url
from app.domains.audit.controllers import record_audit_event
from app.domains.communications.controllers import enqueue_email
from app.domains.communications.models import EmailDelivery
from app.domains.communications.schemas import EmailMessage
from app.domains.communications.services import EmailTemplateRenderer
from app.domains.identity.models import AuthSession, Membership, MembershipStatus, User
from app.domains.identity.repositories import SQLAlchemyIdentityRepository
from app.domains.identity.schemas import SessionIdentity
from app.domains.tenants.schemas import (
    CheckInReminderCandidate,
    CheckInReminderCommand,
    CheckInReminderOverview,
    CheckInReminderPreview,
    CheckInReminderResult,
    CheckInReminderSkip,
)

TEMPLATE_KEY = "check_in_reminder"
identity_repository = SQLAlchemyIdentityRepository()


@dataclass(frozen=True, slots=True)
class _MemberActivity:
    membership: Membership
    user: User
    last_signed_in_at: datetime | None
    last_reminded_at: datetime | None
    reminder_count: int


def cooldown_until(
    last_reminded_at: datetime | None,
    cooldown_hours: int,
    now: datetime,
) -> datetime | None:
    """When this person may next be reminded, or None if they may be reminded now."""
    if last_reminded_at is None:
        return None
    available_at = last_reminded_at + timedelta(hours=cooldown_hours)
    return available_at if available_at > now else None


def is_inactive(
    last_signed_in_at: datetime | None,
    inactive_days: int | None,
    now: datetime,
) -> bool:
    """True when the person never signed in, or not within the last ``inactive_days``."""
    if inactive_days is None:
        return True
    return last_signed_in_at is None or last_signed_in_at <= now - timedelta(days=inactive_days)


def _subject(tenant_name: str) -> str:
    return f"Reminder: check in to {tenant_name} on TRANSPIRE"


def _template_data(
    *,
    recipient_name: str,
    tenant: ResolvedTenant,
    settings: Settings,
) -> dict[str, object]:
    return {
        "recipient_name": recipient_name,
        "tenant_name": tenant.name,
        "action_url": tenant_frontend_url(settings, tenant.slug, "/sign-in"),
        "action_label": "Sign in to TRANSPIRE",
        **preferences_link(settings, tenant.slug),
    }


async def last_sign_ins(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_ids: list[uuid.UUID],
) -> dict[uuid.UUID, datetime]:
    """When each user last signed in to this workspace (start of their latest full session)."""
    if not user_ids:
        return {}
    rows = await session.execute(
        select(AuthSession.user_id, func.max(AuthSession.created_at))
        .where(
            AuthSession.tenant_id == tenant_id,
            AuthSession.user_id.in_(user_ids),
            AuthSession.scope == "full",
        )
        .group_by(AuthSession.user_id)
    )
    return dict(rows.all())


async def _member_activity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    membership_ids: list[uuid.UUID] | None = None,
    lock: bool = False,
) -> list[_MemberActivity]:
    members_query = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .order_by(User.display_name, User.email)
    )
    if membership_ids is not None:
        members_query = members_query.where(Membership.id.in_(membership_ids))
    if lock:
        # Serialises concurrent sends to the same people so the cooldown check
        # below always sees reminders another administrator just committed.
        members_query = members_query.with_for_update(of=Membership)
    members = (await session.execute(members_query)).all()
    if not members:
        return []

    user_ids = [user.id for _, user in members]
    emails = [user.email for _, user in members]
    sign_ins = await last_sign_ins(session, tenant_id, user_ids)
    reminders = {
        recipient: (last_sent, count)
        for recipient, last_sent, count in (
            await session.execute(
                select(
                    EmailDelivery.recipient,
                    func.max(EmailDelivery.created_at),
                    func.count(EmailDelivery.id),
                )
                .where(
                    EmailDelivery.tenant_id == tenant_id,
                    EmailDelivery.template_key == TEMPLATE_KEY,
                    EmailDelivery.recipient.in_(emails),
                )
                .group_by(EmailDelivery.recipient)
            )
        ).all()
    }
    return [
        _MemberActivity(
            membership=membership,
            user=user,
            last_signed_in_at=sign_ins.get(user.id),
            last_reminded_at=reminders.get(user.email, (None, 0))[0],
            reminder_count=int(reminders.get(user.email, (None, 0))[1]),
        )
        for membership, user in members
    ]


async def list_check_in_candidates(
    tenant_id: uuid.UUID,
    settings: Settings,
    session: AsyncSession,
    *,
    inactive_days: int | None = None,
) -> CheckInReminderOverview:
    now = datetime.now(UTC)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        activity = await _member_activity(session, tenant_id)
        candidates = [
            CheckInReminderCandidate(
                membership_id=record.membership.id,
                email=record.user.email,
                display_name=record.user.display_name,
                roles=await identity_repository.get_role_keys(
                    session, tenant_id, record.membership.id
                ),
                last_signed_in_at=record.last_signed_in_at,
                last_reminded_at=record.last_reminded_at,
                reminder_count=record.reminder_count,
                cooldown_until=cooldown_until(
                    record.last_reminded_at, settings.check_in_reminder_cooldown_hours, now
                ),
            )
            for record in activity
            if is_inactive(record.last_signed_in_at, inactive_days, now)
        ]
    return CheckInReminderOverview(
        cooldown_hours=settings.check_in_reminder_cooldown_hours,
        candidates=candidates,
    )


def preview_check_in_reminder(
    identity: SessionIdentity,
    tenant: ResolvedTenant,
    settings: Settings,
) -> CheckInReminderPreview:
    rendered = EmailTemplateRenderer(public_app_url=settings.public_app_url).render(
        EmailMessage(
            tenant_id=tenant.tenant_id,
            recipient=identity.user.email,
            template_key=TEMPLATE_KEY,
            subject=_subject(tenant.name),
            template_data=_template_data(
                recipient_name="Colleague",
                tenant=tenant,
                settings=settings,
            ),
        )
    )
    return CheckInReminderPreview(
        subject=rendered.subject,
        html_body=rendered.html_body,
        text_body=rendered.text_body,
    )


async def send_check_in_reminders(
    command: CheckInReminderCommand,
    identity: SessionIdentity,
    tenant: ResolvedTenant,
    settings: Settings,
    session: AsyncSession,
) -> CheckInReminderResult:
    requested = list(dict.fromkeys(command.membership_ids))
    batch_id = uuid.uuid4()
    queued: list[uuid.UUID] = []
    skipped: list[CheckInReminderSkip] = []
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        now = datetime.now(UTC)
        activity = {
            record.membership.id: record
            for record in await _member_activity(
                session, tenant.tenant_id, membership_ids=requested, lock=True
            )
        }
        for membership_id in requested:
            record = activity.get(membership_id)
            if record is None:
                skipped.append(
                    CheckInReminderSkip(membership_id=membership_id, reason="not_eligible")
                )
                continue
            if cooldown_until(
                record.last_reminded_at, settings.check_in_reminder_cooldown_hours, now
            ):
                skipped.append(CheckInReminderSkip(membership_id=membership_id, reason="cooldown"))
                continue
            enqueue_email(
                session,
                EmailMessage(
                    tenant_id=tenant.tenant_id,
                    recipient=record.user.email,
                    template_key=TEMPLATE_KEY,
                    subject=_subject(tenant.name),
                    correlation_id=batch_id,
                    template_data=_template_data(
                        recipient_name=record.user.display_name,
                        tenant=tenant,
                        settings=settings,
                    ),
                ),
                settings,
            )
            record_audit_event(
                session,
                tenant_id=tenant.tenant_id,
                actor_user_id=identity.user.id,
                subject_user_id=record.user.id,
                event_type="check_in_reminder.sent",
                entity_type="membership",
                entity_id=membership_id,
                entity_reference=None,
                summary=f"Check-in reminder sent to {record.user.display_name}",
                details={"batch_id": str(batch_id)},
            )
            queued.append(membership_id)
    return CheckInReminderResult(queued=queued, skipped=skipped)
