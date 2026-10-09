import logging
from datetime import UTC, datetime, timedelta

from app.core.config import Settings, get_settings
from app.core.database import session_factory
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.communications.models import EmailDelivery, EmailDeliveryStatus
from app.domains.communications.repositories import SQLAlchemyEmailDeliveryRepository
from app.domains.communications.schemas import EmailMessage
from app.domains.communications.security import decrypt_template_data
from app.domains.communications.services import build_email_service

logger = logging.getLogger(__name__)
repository = SQLAlchemyEmailDeliveryRepository()


async def _claim(settings: Settings) -> EmailDelivery | None:
    async with session_factory() as session, session.begin():
        return await repository.claim_next(
            session,
            lease_seconds=settings.outbox_lease_seconds,
        )


async def _mark_sent(delivery: EmailDelivery, provider_message_id: str) -> None:
    async with session_factory() as session, session.begin():
        await apply_tenant_to_transaction(session, delivery.tenant_id)
        current = await repository.get_for_tenant(session, delivery.tenant_id, delivery.id)
        if current is None:
            return
        current.status = EmailDeliveryStatus.SENT
        current.provider_message_id = provider_message_id
        current.sent_at = datetime.now(UTC)
        current.locked_at = None
        current.last_error = None


async def _mark_failed(
    delivery: EmailDelivery,
    error: Exception,
    settings: Settings,
) -> None:
    async with session_factory() as session, session.begin():
        await apply_tenant_to_transaction(session, delivery.tenant_id)
        current = await repository.get_for_tenant(session, delivery.tenant_id, delivery.id)
        if current is None:
            return
        current.last_error = f"{type(error).__name__}: {error}"[:2000]
        current.locked_at = None
        if current.attempt_count >= settings.outbox_max_attempts:
            current.status = EmailDeliveryStatus.FAILED
            return
        current.status = EmailDeliveryStatus.QUEUED
        delay = settings.outbox_retry_base_seconds * (2 ** (current.attempt_count - 1))
        current.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)


async def process_next_email(settings: Settings | None = None) -> bool:
    resolved_settings = settings or get_settings()
    delivery = await _claim(resolved_settings)
    if delivery is None:
        return False

    try:
        template_data = dict(delivery.template_data)
        if delivery.encrypted_template_data:
            template_data.update(
                decrypt_template_data(delivery.encrypted_template_data, resolved_settings)
            )
        message = EmailMessage(
            tenant_id=delivery.tenant_id,
            recipient=delivery.recipient,
            template_key=delivery.template_key,
            subject=delivery.subject,
            template_data=template_data,
            correlation_id=delivery.correlation_id,
        )
        result = await build_email_service(resolved_settings).send(message)
    except Exception as error:
        logger.exception(
            "Transactional email delivery failed",
            extra={"delivery_id": str(delivery.id)},
        )
        await _mark_failed(delivery, error, resolved_settings)
    else:
        await _mark_sent(delivery, result.provider_message_id)
    return True


async def process_email_batch(
    *,
    limit: int = 25,
    settings: Settings | None = None,
) -> int:
    processed = 0
    for _ in range(limit):
        if not await process_next_email(settings):
            break
        processed += 1
    return processed
