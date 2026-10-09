import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.ideas.models import IdeaBankPolicy


def create_default_idea_bank_policy(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    session.add(
        IdeaBankPolicy(
            tenant_id=tenant_id,
            detail_level="operational",
            show_contributor=True,
            show_financials=False,
        )
    )
