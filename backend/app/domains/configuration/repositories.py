import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.configuration.models import (
    ConfigurationItem,
    DepartmentSite,
    WorkflowDefinition,
    WorkflowVersion,
)
from app.domains.identity.models import InvitationToken, Membership, MembershipStatus, User


@dataclass(frozen=True, slots=True)
class WorkflowAssigneeRecord:
    membership: Membership
    user: User
    status: str


class SQLAlchemyConfigurationRepository:
    async def list_workflow_assignees(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> list[WorkflowAssigneeRecord]:
        pending_invitation = exists(
            select(InvitationToken.id).where(
                InvitationToken.tenant_id == tenant_id,
                InvitationToken.email == User.email,
                InvitationToken.accepted_at.is_(None),
                InvitationToken.revoked_at.is_(None),
                InvitationToken.expires_at > datetime.now(UTC),
            )
        )
        rows = (
            await session.execute(
                select(Membership, User)
                .join(User, User.id == Membership.user_id)
                .where(
                    Membership.tenant_id == tenant_id,
                    or_(
                        Membership.status == MembershipStatus.ACTIVE,
                        and_(
                            Membership.status == MembershipStatus.INVITED,
                            pending_invitation,
                        ),
                    ),
                )
                .order_by(User.display_name, User.email)
            )
        ).all()
        return [
            WorkflowAssigneeRecord(
                membership=membership,
                user=user,
                status=("active" if membership.status == MembershipStatus.ACTIVE else "pending"),
            )
            for membership, user in rows
        ]

    async def list_items(
        self, session: AsyncSession, tenant_id: uuid.UUID, kind: str
    ) -> list[ConfigurationItem]:
        return list(
            (
                await session.scalars(
                    select(ConfigurationItem)
                    .where(ConfigurationItem.tenant_id == tenant_id, ConfigurationItem.kind == kind)
                    .order_by(ConfigurationItem.sort_order, ConfigurationItem.name)
                )
            ).all()
        )

    async def get_item(
        self, session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> ConfigurationItem | None:
        return await session.scalar(
            select(ConfigurationItem)
            .where(ConfigurationItem.tenant_id == tenant_id, ConfigurationItem.id == item_id)
            .with_for_update()
        )

    async def active_children(
        self, session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> int:
        direct_children = int(
            await session.scalar(
                select(func.count())
                .select_from(ConfigurationItem)
                .where(
                    ConfigurationItem.tenant_id == tenant_id,
                    ConfigurationItem.parent_id == item_id,
                    ConfigurationItem.is_active.is_(True),
                )
            )
            or 0
        )
        assigned_departments = int(
            await session.scalar(
                select(func.count())
                .select_from(DepartmentSite)
                .join(ConfigurationItem, ConfigurationItem.id == DepartmentSite.department_id)
                .where(
                    DepartmentSite.tenant_id == tenant_id,
                    DepartmentSite.site_id == item_id,
                    ConfigurationItem.is_active.is_(True),
                )
            )
            or 0
        )
        return direct_children + assigned_departments

    async def department_site_ids(
        self, session: AsyncSession, tenant_id: uuid.UUID, department_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        if not department_ids:
            return {}
        rows = (
            await session.execute(
                select(DepartmentSite.department_id, DepartmentSite.site_id)
                .where(
                    DepartmentSite.tenant_id == tenant_id,
                    DepartmentSite.department_id.in_(department_ids),
                )
                .order_by(DepartmentSite.created_at)
            )
        ).all()
        result: dict[uuid.UUID, list[uuid.UUID]] = {}
        for department_id, site_id in rows:
            result.setdefault(department_id, []).append(site_id)
        return result

    async def replace_department_sites(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        department_id: uuid.UUID,
        site_ids: list[uuid.UUID],
    ) -> None:
        await session.execute(
            delete(DepartmentSite).where(
                DepartmentSite.tenant_id == tenant_id,
                DepartmentSite.department_id == department_id,
            )
        )
        session.add_all(
            DepartmentSite(tenant_id=tenant_id, department_id=department_id, site_id=site_id)
            for site_id in site_ids
        )

    async def list_workflows(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> list[tuple[WorkflowDefinition, list[WorkflowVersion]]]:
        definitions = list(
            (
                await session.scalars(
                    select(WorkflowDefinition)
                    .where(WorkflowDefinition.tenant_id == tenant_id)
                    .order_by(WorkflowDefinition.name)
                )
            ).all()
        )
        result: list[tuple[WorkflowDefinition, list[WorkflowVersion]]] = []
        for definition in definitions:
            versions = list(
                (
                    await session.scalars(
                        select(WorkflowVersion)
                        .where(
                            WorkflowVersion.tenant_id == tenant_id,
                            WorkflowVersion.workflow_id == definition.id,
                        )
                        .order_by(WorkflowVersion.version.desc())
                    )
                ).all()
            )
            result.append((definition, versions))
        return result

    async def get_workflow(
        self, session: AsyncSession, tenant_id: uuid.UUID, workflow_id: uuid.UUID
    ) -> WorkflowDefinition | None:
        return await session.scalar(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.tenant_id == tenant_id, WorkflowDefinition.id == workflow_id)
            .with_for_update()
        )

    async def get_version(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        workflow_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> WorkflowVersion | None:
        return await session.scalar(
            select(WorkflowVersion)
            .where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.workflow_id == workflow_id,
                WorkflowVersion.id == version_id,
            )
            .with_for_update()
        )

    async def next_version(self, session: AsyncSession, workflow_id: uuid.UUID) -> int:
        return int(
            await session.scalar(
                select(func.coalesce(func.max(WorkflowVersion.version), 0) + 1).where(
                    WorkflowVersion.workflow_id == workflow_id
                )
            )
            or 1
        )
