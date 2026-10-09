import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.audit.models import AuditEvent
from app.domains.audit.schemas import AuditEventPage, AuditEventRecord
from app.domains.identity.models import User


def record_audit_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    subject_user_id: uuid.UUID | None,
    event_type: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    entity_reference: str | None,
    summary: str,
    details: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            subject_user_id=subject_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_reference=entity_reference,
            summary=summary,
            details=details or {},
        )
    )


async def list_audit_events(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    is_tenant_admin: bool,
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    query: str = "",
) -> AuditEventPage:
    actor = aliased(User)
    subject = aliased(User)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        filters = [AuditEvent.tenant_id == tenant_id]
        if not is_tenant_admin:
            filters.append(
                or_(AuditEvent.actor_user_id == user_id, AuditEvent.subject_user_id == user_id)
            )
        term = query.strip()
        if term:
            pattern = f"%{term}%"
            filters.append(
                or_(
                    AuditEvent.summary.ilike(pattern),
                    AuditEvent.event_type.ilike(pattern),
                    AuditEvent.entity_reference.ilike(pattern),
                    actor.display_name.ilike(pattern),
                    actor.email.ilike(pattern),
                )
            )
        joined = (
            select(AuditEvent, actor, subject)
            .outerjoin(actor, actor.id == AuditEvent.actor_user_id)
            .outerjoin(subject, subject.id == AuditEvent.subject_user_id)
            .where(*filters)
        )
        total = int(
            await session.scalar(select(func.count()).select_from(joined.order_by(None).subquery()))
            or 0
        )
        rows = (
            await session.execute(
                joined.order_by(AuditEvent.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return AuditEventPage(
            items=[
                AuditEventRecord(
                    id=event.id,
                    event_type=event.event_type,
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    entity_reference=event.entity_reference,
                    summary=event.summary,
                    details=event.details,
                    actor_name=actor_user.display_name if actor_user else None,
                    actor_email=actor_user.email if actor_user else None,
                    subject_name=subject_user.display_name if subject_user else None,
                    created_at=event.created_at,
                )
                for event, actor_user, subject_user in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
            tenant_scope=is_tenant_admin,
        )
