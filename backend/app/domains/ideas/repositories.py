import uuid

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domains.configuration.models import ConfigurationItem
from app.domains.ideas.models import Idea, IdeaBankPolicy, IdeaStatus
from app.domains.identity.models import User


class SQLAlchemyIdeaRepository:
    async def get_draft(
        self, session: AsyncSession, tenant_id: uuid.UUID, idea_id: uuid.UUID, user_id: uuid.UUID
    ) -> Idea | None:
        return await session.scalar(
            select(Idea)
            .where(
                Idea.tenant_id == tenant_id,
                Idea.id == idea_id,
                Idea.submitter_user_id == user_id,
                Idea.status == IdeaStatus.DRAFT,
            )
            .with_for_update()
        )

    async def get_editable(
        self, session: AsyncSession, tenant_id: uuid.UUID, idea_id: uuid.UUID, user_id: uuid.UUID
    ) -> Idea | None:
        return await session.scalar(
            select(Idea)
            .where(
                Idea.tenant_id == tenant_id,
                Idea.id == idea_id,
                Idea.submitter_user_id == user_id,
                Idea.status.in_([IdeaStatus.DRAFT, IdeaStatus.NEEDS_CORRECTION]),
            )
            .with_for_update()
        )

    async def list_bank(self, session: AsyncSession, tenant_id: uuid.UUID):
        category = aliased(ConfigurationItem)
        subcategory = aliased(ConfigurationItem)
        process_area = aliased(ConfigurationItem)
        statement: Select = (
            select(Idea, User.display_name, category.name, subcategory.name, process_area.name)
            .join(User, User.id == Idea.submitter_user_id)
            .outerjoin(category, category.id == Idea.category_id)
            .outerjoin(subcategory, subcategory.id == Idea.subcategory_id)
            .outerjoin(process_area, process_area.id == Idea.process_area_id)
            .where(
                Idea.tenant_id == tenant_id,
                Idea.status.in_(
                    [
                        IdeaStatus.SUBMITTED,
                        IdeaStatus.APPROVED,
                        IdeaStatus.CHARTER_IN_PROGRESS,
                        IdeaStatus.CHARTER_SUBMITTED,
                    ]
                ),
            )
            .order_by(Idea.submitted_at.desc())
        )
        return list((await session.execute(statement)).all())

    async def get_policy(
        self, session: AsyncSession, tenant_id: uuid.UUID, *, lock: bool = False
    ) -> IdeaBankPolicy | None:
        statement = select(IdeaBankPolicy).where(IdeaBankPolicy.tenant_id == tenant_id)
        if lock:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def get_catalog_items(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> list[ConfigurationItem]:
        return list(
            (
                await session.scalars(
                    select(ConfigurationItem)
                    .where(
                        ConfigurationItem.tenant_id == tenant_id,
                        ConfigurationItem.is_active.is_(True),
                        or_(
                            ConfigurationItem.kind == "site",
                            ConfigurationItem.kind == "department",
                            ConfigurationItem.kind == "category",
                            ConfigurationItem.kind == "subcategory",
                            ConfigurationItem.kind == "process_area",
                        ),
                    )
                    .order_by(ConfigurationItem.sort_order, ConfigurationItem.name)
                )
            ).all()
        )
