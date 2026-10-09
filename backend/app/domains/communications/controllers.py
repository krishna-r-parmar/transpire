from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domains.communications.models import EmailDelivery
from app.domains.communications.schemas import EmailMessage
from app.domains.communications.security import encrypt_template_data


def enqueue_email(
    session: AsyncSession,
    message: EmailMessage,
    settings: Settings,
    *,
    sensitive_template_data: dict[str, object] | None = None,
) -> EmailDelivery:
    delivery = EmailDelivery(
        tenant_id=message.tenant_id,
        correlation_id=message.correlation_id,
        template_key=message.template_key,
        recipient=str(message.recipient),
        subject=message.subject,
        template_data=message.template_data,
        encrypted_template_data=(
            encrypt_template_data(sensitive_template_data, settings)
            if sensitive_template_data
            else None
        ),
    )
    session.add(delivery)
    return delivery
