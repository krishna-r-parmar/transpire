import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.communications.models import EmailDelivery


class SQLAlchemyEmailDeliveryRepository:
    async def claim_next(
        self,
        session: AsyncSession,
        *,
        lease_seconds: int,
    ) -> EmailDelivery | None:
        row = (
            (
                await session.execute(
                    text("SELECT * FROM claim_email_delivery(:lease_seconds)"),
                    {"lease_seconds": lease_seconds},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        tenant_id = uuid.UUID(str(row["resolved_tenant_id"]))
        await apply_tenant_to_transaction(session, tenant_id)
        return await session.scalar(
            select(EmailDelivery).where(EmailDelivery.id == row["delivery_id"])
        )

    async def get_for_tenant(
        self,
        session: AsyncSession,
        tenant_id: object,
        delivery_id: object,
    ) -> EmailDelivery | None:
        return await session.scalar(
            select(EmailDelivery).where(
                EmailDelivery.tenant_id == tenant_id,
                EmailDelivery.id == delivery_id,
            )
        )
