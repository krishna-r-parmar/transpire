import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import (
    AuthSession,
    InvitationToken,
    Membership,
    MembershipStatus,
    PasswordResetToken,
    Role,
    User,
    WorkspaceSelectionToken,
    membership_roles,
)


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    user: User
    membership: Membership


@dataclass(frozen=True, slots=True)
class SessionRecord:
    auth_session: AuthSession
    user: User
    membership: Membership


@dataclass(frozen=True, slots=True)
class PasswordResetRecord:
    reset_token: PasswordResetToken
    user: User
    membership: Membership


@dataclass(frozen=True, slots=True)
class InvitationRecord:
    invitation: InvitationToken
    user: User
    membership: Membership


@dataclass(frozen=True, slots=True)
class GlobalSignInUser:
    id: uuid.UUID
    email: str
    display_name: str
    password_hash: str | None
    is_platform_admin: bool
    failed_sign_in_attempts: int
    locked_until: datetime | None


@dataclass(frozen=True, slots=True)
class UserWorkspace:
    membership_id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    name: str


class SQLAlchemyIdentityRepository:
    async def tenant_requires_sso(self, session: AsyncSession, tenant_id: uuid.UUID) -> bool:
        return bool(
            await session.scalar(
                text("SELECT tenant_requires_sso_global(:tenant_id)"),
                {"tenant_id": tenant_id},
            )
        )

    async def get_global_sign_in_user(
        self, session: AsyncSession, email: str
    ) -> GlobalSignInUser | None:
        row = (
            await session.execute(
                text("SELECT * FROM lookup_global_sign_in_user(:email)"),
                {"email": email},
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        return GlobalSignInUser(
            id=row["user_id"],
            email=row["email"],
            display_name=row["display_name"],
            password_hash=row["password_hash"],
            is_platform_admin=row["is_platform_admin"],
            failed_sign_in_attempts=row["failed_sign_in_attempts"],
            locked_until=row["locked_until"],
        )

    async def list_active_user_workspaces(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> list[UserWorkspace]:
        rows = (
            await session.execute(
                text("SELECT * FROM list_active_user_workspaces(:user_id)"),
                {"user_id": user_id},
            )
        ).mappings().all()
        return [
            UserWorkspace(
                membership_id=row["membership_id"],
                tenant_id=row["tenant_id"],
                slug=row["slug"],
                name=row["name"],
            )
            for row in rows
        ]

    async def get_workspace_selection_token(
        self,
        session: AsyncSession,
        token_hash: str,
        now: datetime,
    ) -> WorkspaceSelectionToken | None:
        return await session.scalar(
            select(WorkspaceSelectionToken)
            .where(
                WorkspaceSelectionToken.token_hash == token_hash,
                WorkspaceSelectionToken.consumed_at.is_(None),
                WorkspaceSelectionToken.expires_at > now,
            )
            .with_for_update()
        )

    async def get_identity_by_email(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        email: str,
    ) -> IdentityRecord | None:
        statement: Select[tuple[User, Membership]] = (
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.tenant_id == tenant_id, User.email == email)
        )
        row = (await session.execute(statement)).one_or_none()
        return IdentityRecord(user=row[0], membership=row[1]) if row else None

    async def get_session(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        token_hash: str,
        now: datetime,
    ) -> SessionRecord | None:
        statement: Select[tuple[AuthSession, User, Membership]] = (
            select(AuthSession, User, Membership)
            .join(User, User.id == AuthSession.user_id)
            .join(
                Membership,
                (Membership.user_id == User.id) & (Membership.tenant_id == tenant_id),
            )
            .where(
                AuthSession.tenant_id == tenant_id,
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        row = (await session.execute(statement)).one_or_none()
        return SessionRecord(auth_session=row[0], user=row[1], membership=row[2]) if row else None

    async def get_role_keys(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        membership_id: uuid.UUID,
    ) -> list[str]:
        statement = (
            select(Role.key)
            .join(membership_roles, membership_roles.c.role_id == Role.id)
            .where(
                Role.tenant_id == tenant_id,
                membership_roles.c.membership_id == membership_id,
            )
            .order_by(Role.key)
        )
        return list((await session.scalars(statement)).all())

    async def expire_password_reset_tokens(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        consumed_at: datetime,
    ) -> None:
        await session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.tenant_id == tenant_id,
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.consumed_at.is_(None),
            )
            .values(consumed_at=consumed_at)
        )

    async def get_password_reset_token(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        token_hash: str,
        now: datetime,
    ) -> PasswordResetRecord | None:
        statement: Select[tuple[PasswordResetToken, User, Membership]] = (
            select(PasswordResetToken, User, Membership)
            .join(User, User.id == PasswordResetToken.user_id)
            .join(
                Membership,
                (Membership.user_id == User.id) & (Membership.tenant_id == tenant_id),
            )
            .where(
                PasswordResetToken.tenant_id == tenant_id,
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.consumed_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
            .with_for_update()
        )
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        return PasswordResetRecord(reset_token=row[0], user=row[1], membership=row[2])

    async def revoke_user_sessions(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        await session.execute(
            update(AuthSession)
            .where(
                AuthSession.tenant_id == tenant_id,
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

    async def get_invitation(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        token_hash: str,
        now: datetime,
        *,
        for_update: bool,
    ) -> InvitationRecord | None:
        statement: Select[tuple[InvitationToken, User, Membership]] = (
            select(InvitationToken, User, Membership)
            .join(User, User.email == InvitationToken.email)
            .join(
                Membership,
                (Membership.user_id == User.id) & (Membership.tenant_id == tenant_id),
            )
            .where(
                InvitationToken.tenant_id == tenant_id,
                InvitationToken.token_hash == token_hash,
                InvitationToken.accepted_at.is_(None),
                InvitationToken.revoked_at.is_(None),
                InvitationToken.expires_at > now,
                Membership.status == MembershipStatus.INVITED,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        return InvitationRecord(invitation=row[0], user=row[1], membership=row[2])
