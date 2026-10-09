import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import (
    InvitationToken,
    Membership,
    Role,
    User,
    membership_roles,
)
from app.domains.tenants.models import Tenant


@dataclass(frozen=True, slots=True)
class TenantMemberRecord:
    membership: Membership
    user: User


@dataclass(frozen=True, slots=True)
class InvitationManagementRecord:
    invitation: InvitationToken
    membership: Membership
    user: User
    role: Role


class SQLAlchemyTenantRepository:
    async def list_platform_tenants(self, session: AsyncSession):
        result = await session.execute(text("SELECT * FROM list_platform_tenants()"))
        return list(result.mappings().all())

    async def list_platform_tenant_invitations(self, session: AsyncSession):
        result = await session.execute(text("SELECT * FROM list_platform_tenant_invitations()"))
        return list(result.mappings().all())

    async def ensure_invited_user(
        self,
        session: AsyncSession,
        email: str,
        display_name: str,
    ) -> uuid.UUID:
        value = await session.scalar(
            text("SELECT ensure_invited_user(:email, :display_name)"),
            {"email": email, "display_name": display_name},
        )
        return uuid.UUID(str(value))

    async def get_tenant(self, session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
        return await session.scalar(select(Tenant).where(Tenant.id == tenant_id))

    async def get_role(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        role_key: str,
    ) -> Role | None:
        return await session.scalar(
            select(Role).where(Role.tenant_id == tenant_id, Role.key == role_key)
        )

    async def get_membership(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Membership | None:
        return await session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == user_id,
            )
        )

    async def get_membership_by_id(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        membership_id: uuid.UUID,
    ) -> TenantMemberRecord | None:
        row = (
            await session.execute(
                select(Membership, User)
                .join(User, User.id == Membership.user_id)
                .where(
                    Membership.tenant_id == tenant_id,
                    Membership.id == membership_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        return TenantMemberRecord(membership=row[0], user=row[1]) if row else None

    async def get_invitation(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        invitation_id: uuid.UUID,
    ) -> InvitationManagementRecord | None:
        row = (
            await session.execute(
                select(InvitationToken, Membership, User, Role)
                .join(User, User.email == InvitationToken.email)
                .join(
                    Membership,
                    (Membership.user_id == User.id)
                    & (Membership.tenant_id == InvitationToken.tenant_id),
                )
                .join(
                    membership_roles,
                    membership_roles.c.membership_id == Membership.id,
                )
                .join(Role, Role.id == membership_roles.c.role_id)
                .where(
                    InvitationToken.tenant_id == tenant_id,
                    InvitationToken.id == invitation_id,
                    InvitationToken.accepted_at.is_(None),
                )
                .with_for_update()
            )
        ).one_or_none()
        if row is None:
            return None
        return InvitationManagementRecord(
            invitation=row[0],
            membership=row[1],
            user=row[2],
            role=row[3],
        )

    async def list_invitations(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> list[InvitationManagementRecord]:
        rows = (
            await session.execute(
                select(InvitationToken, Membership, User, Role)
                .join(User, User.email == InvitationToken.email)
                .join(
                    Membership,
                    (Membership.user_id == User.id)
                    & (Membership.tenant_id == InvitationToken.tenant_id),
                )
                .join(
                    membership_roles,
                    membership_roles.c.membership_id == Membership.id,
                )
                .join(Role, Role.id == membership_roles.c.role_id)
                .where(
                    InvitationToken.tenant_id == tenant_id,
                    InvitationToken.accepted_at.is_(None),
                )
                .order_by(InvitationToken.created_at.desc())
            )
        ).all()
        latest_by_email: dict[str, InvitationManagementRecord] = {}
        for row in rows:
            record = InvitationManagementRecord(
                invitation=row[0], membership=row[1], user=row[2], role=row[3]
            )
            latest_by_email.setdefault(record.user.email, record)
        return list(latest_by_email.values())

    async def list_members(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> list[TenantMemberRecord]:
        rows = (
            await session.execute(
                select(Membership, User)
                .join(User, User.id == Membership.user_id)
                .where(Membership.tenant_id == tenant_id)
                .order_by(User.display_name, User.email)
            )
        ).all()
        return [TenantMemberRecord(membership=row[0], user=row[1]) for row in rows]

    async def list_roles(self, session: AsyncSession, tenant_id: uuid.UUID) -> list[Role]:
        return list(
            (
                await session.scalars(
                    select(Role).where(Role.tenant_id == tenant_id).order_by(Role.name)
                )
            ).all()
        )
