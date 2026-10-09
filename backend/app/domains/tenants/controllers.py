import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.core.urls import platform_frontend_url
from app.domains.communications.controllers import enqueue_email
from app.domains.communications.models import EmailDelivery, EmailDeliveryStatus
from app.domains.communications.schemas import EmailMessage
from app.domains.configuration.controllers import (
    create_default_master_data,
    create_default_workflow,
)
from app.domains.ideas.services import create_default_idea_bank_policy
from app.domains.identity.models import (
    AuthSession,
    InvitationToken,
    Membership,
    MembershipStatus,
    Role,
    membership_roles,
)
from app.domains.identity.repositories import SQLAlchemyIdentityRepository
from app.domains.identity.schemas import SessionIdentity
from app.domains.identity.services import generate_session_token, hash_session_token
from app.domains.tenants.models import Tenant, TenantStatus
from app.domains.tenants.repositories import SQLAlchemyTenantRepository
from app.domains.tenants.schemas import (
    InvitationCreateCommand,
    InvitationResult,
    InvitationSummary,
    PlatformTenantSummary,
    TenantMemberSummary,
    TenantProvisionCommand,
    TenantProvisionResult,
    TenantRoleSummary,
)


class TenantConflictError(Exception):
    pass


class InvitationConflictError(Exception):
    pass


class RoleNotFoundError(Exception):
    pass


class InvitationNotFoundError(Exception):
    pass


class MembershipConflictError(Exception):
    pass


repository = SQLAlchemyTenantRepository()
identity_repository = SQLAlchemyIdentityRepository()

SYSTEM_ROLES = (
    (
        "tenant_admin",
        "Tenant Administrator",
        ["idea.create", "idea.view", "tenant.people.manage", "tenant.settings.manage"],
    ),
    ("idea_submitter", "Idea Submitter", ["idea.create", "idea.view"]),
)


async def _discard_queued_invitation_emails(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    recipient: str | None = None,
) -> None:
    conditions = [
        EmailDelivery.tenant_id == tenant_id,
        EmailDelivery.template_key == "invitation",
        EmailDelivery.status == EmailDeliveryStatus.QUEUED,
    ]
    if recipient is not None:
        conditions.append(EmailDelivery.recipient == recipient)
    await session.execute(delete(EmailDelivery).where(*conditions))


async def _create_system_roles(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for key, name, permissions in SYSTEM_ROLES:
        role = Role(
            tenant_id=tenant_id,
            key=key,
            name=name,
            permissions=permissions,
            is_system=True,
        )
        session.add(role)
        roles[key] = role
    await session.flush()
    return roles


async def _queue_invitation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    tenant_name: str,
    email: str,
    display_name: str,
    inviter: SessionIdentity,
    role: Role,
    settings: Settings,
) -> InvitationResult:
    user_id = await repository.ensure_invited_user(session, email, display_name)
    membership = await repository.get_membership(session, tenant_id, user_id)
    if membership and membership.status == MembershipStatus.ACTIVE:
        raise InvitationConflictError("This person is already an active member")
    if membership is None:
        membership = Membership(
            tenant_id=tenant_id,
            user_id=user_id,
            status=MembershipStatus.INVITED,
        )
        session.add(membership)
        await session.flush()
    else:
        membership.status = MembershipStatus.INVITED
        membership.failed_sign_in_attempts = 0
        membership.locked_until = None

    await session.execute(
        delete(membership_roles).where(membership_roles.c.membership_id == membership.id)
    )
    await session.execute(
        insert(membership_roles).values(membership_id=membership.id, role_id=role.id)
    )
    now = datetime.now(UTC)
    await session.execute(
        update(InvitationToken)
        .where(
            InvitationToken.tenant_id == tenant_id,
            InvitationToken.email == email,
            InvitationToken.accepted_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await _discard_queued_invitation_emails(session, tenant_id, recipient=email)
    raw_token = f"{tenant_id}.{generate_session_token()}"
    expires_at = now + timedelta(hours=settings.invitation_expiry_hours)
    invitation = InvitationToken(
        tenant_id=tenant_id,
        email=email,
        invited_by_user_id=inviter.user.id,
        token_hash=hash_session_token(raw_token),
        expires_at=expires_at,
        last_sent_at=now,
    )
    session.add(invitation)
    enqueue_email(
        session,
        EmailMessage(
            tenant_id=tenant_id,
            recipient=email,
            template_key="invitation",
            subject=f"You are invited to {tenant_name} on TRANSPIRE",
            template_data={
                "recipient_name": display_name,
                "tenant_name": tenant_name,
                "inviter_name": inviter.user.display_name,
                "expires_in": f"{settings.invitation_expiry_hours} hours",
                "action_label": "Accept invitation",
            },
        ),
        settings,
        sensitive_template_data={
            "action_url": platform_frontend_url(
                settings,
                "/accept-invitation",
                query={"token": raw_token},
            )
        },
    )
    await session.flush()
    return InvitationResult(
        id=invitation.id,
        email=email,
        display_name=display_name,
        role_key=role.key,
        expires_at=expires_at,
    )


async def list_platform_tenants(session: AsyncSession) -> list[PlatformTenantSummary]:
    rows = await repository.list_platform_tenants(session)
    invitation_rows = await repository.list_platform_tenant_invitations(session)
    invitations = {
        row["tenant_id"]: InvitationSummary(
            id=row["invitation_id"],
            email=row["email"],
            display_name=row["display_name"],
            role_key=row["role_key"] or "tenant_admin",
            status=row["invitation_status"],
            expires_at=row["expires_at"],
            last_sent_at=row["last_sent_at"],
        )
        for row in invitation_rows
    }
    return [
        PlatformTenantSummary(
            id=row["tenant_id"],
            slug=row["slug"],
            name=row["name"],
            status=row["status"],
            created_at=row["created_at"],
            invitation=invitations.get(row["tenant_id"]),
        )
        for row in rows
    ]


async def provision_tenant(
    command: TenantProvisionCommand,
    inviter: SessionIdentity,
    settings: Settings,
    session: AsyncSession,
) -> TenantProvisionResult:
    tenant_id = uuid.uuid4()
    email = str(command.first_admin_email).casefold()
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        tenant = Tenant(
            id=tenant_id,
            slug=command.slug,
            name=command.name,
            status=TenantStatus.ACTIVE,
            settings={},
            branding={},
        )
        session.add(tenant)
        # Establish the FK parent before batching independently constructed
        # tenant-owned records that do not use ORM relationships.
        await session.flush()
        roles = await _create_system_roles(session, tenant_id)
        create_default_master_data(session, tenant_id)
        create_default_workflow(session, tenant_id)
        create_default_idea_bank_policy(session, tenant_id)
        invitation = await _queue_invitation(
            session,
            tenant_id=tenant_id,
            tenant_name=command.name,
            email=email,
            display_name=command.first_admin_name,
            inviter=inviter,
            role=roles["tenant_admin"],
            settings=settings,
        )
    return TenantProvisionResult(
        id=tenant_id,
        slug=command.slug,
        name=command.name,
        status=TenantStatus.ACTIVE,
        invitation_sent_to=invitation.email,
    )


async def change_tenant_status(
    tenant_id: uuid.UUID,
    new_status: TenantStatus,
    current_tenant_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    if tenant_id == current_tenant_id and new_status != TenantStatus.ACTIVE:
        raise TenantConflictError("The active platform workspace cannot suspend itself")
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        tenant = await repository.get_tenant(session, tenant_id)
        if tenant is None:
            raise TenantConflictError("Tenant was not found")
        if tenant.status == TenantStatus.REMOVED:
            raise TenantConflictError("A removed tenant cannot be reactivated here")
        tenant.status = new_status


async def remove_tenant(
    tenant_id: uuid.UUID,
    current_tenant_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    if tenant_id == current_tenant_id:
        raise TenantConflictError("The active platform workspace cannot remove itself")
    now = datetime.now(UTC)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        tenant = await repository.get_tenant(session, tenant_id)
        if tenant is None:
            raise TenantConflictError("Tenant was not found")
        tenant.status = TenantStatus.REMOVED
        await session.execute(
            update(AuthSession)
            .where(AuthSession.tenant_id == tenant_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.execute(
            update(InvitationToken)
            .where(
                InvitationToken.tenant_id == tenant_id,
                InvitationToken.accepted_at.is_(None),
                InvitationToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await _discard_queued_invitation_emails(session, tenant_id)


async def invite_member(
    command: InvitationCreateCommand,
    tenant_id: uuid.UUID,
    tenant_name: str,
    inviter: SessionIdentity,
    settings: Settings,
    session: AsyncSession,
) -> InvitationResult:
    email = str(command.email).casefold()
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        role = await repository.get_role(session, tenant_id, command.role_key)
        if role is None:
            raise RoleNotFoundError
        return await _queue_invitation(
            session,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            email=email,
            display_name=command.display_name,
            inviter=inviter,
            role=role,
            settings=settings,
        )


async def list_members(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> list[TenantMemberSummary]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        members = await repository.list_members(session, tenant_id)
        return [
            TenantMemberSummary(
                id=record.membership.id,
                email=record.user.email,
                display_name=record.user.display_name,
                status=record.membership.status.value,
                roles=await identity_repository.get_role_keys(
                    session,
                    tenant_id,
                    record.membership.id,
                ),
            )
            for record in members
        ]


async def list_roles(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> list[TenantRoleSummary]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        roles = await repository.list_roles(session, tenant_id)
        return [TenantRoleSummary(key=role.key, name=role.name) for role in roles]


def _invitation_summary(record: object, now: datetime) -> InvitationSummary:
    invitation = record.invitation
    invitation_status = (
        "revoked"
        if invitation.revoked_at is not None
        else "expired"
        if invitation.expires_at <= now
        else "pending"
    )
    return InvitationSummary(
        id=invitation.id,
        email=record.user.email,
        display_name=record.user.display_name,
        role_key=record.role.key,
        status=invitation_status,
        expires_at=invitation.expires_at,
        last_sent_at=invitation.last_sent_at,
    )


async def list_invitations(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> list[InvitationSummary]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        records = await repository.list_invitations(session, tenant_id)
        now = datetime.now(UTC)
        return [_invitation_summary(record, now) for record in records]


async def resend_invitation(
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
    inviter: SessionIdentity,
    settings: Settings,
    session: AsyncSession,
) -> InvitationResult:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        record = await repository.get_invitation(session, tenant_id, invitation_id)
        if record is None:
            raise InvitationNotFoundError
        tenant = await repository.get_tenant(session, tenant_id)
        if tenant is None or tenant.status == TenantStatus.REMOVED:
            raise TenantConflictError("The tenant cannot receive invitations")
        return await _queue_invitation(
            session,
            tenant_id=tenant_id,
            tenant_name=tenant.name,
            email=record.user.email,
            display_name=record.user.display_name,
            inviter=inviter,
            role=record.role,
            settings=settings,
        )


async def revoke_invitation(
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        record = await repository.get_invitation(session, tenant_id, invitation_id)
        if record is None:
            raise InvitationNotFoundError
        record.invitation.revoked_at = datetime.now(UTC)
        await _discard_queued_invitation_emails(
            session,
            tenant_id,
            recipient=record.user.email,
        )
        if record.membership.status == MembershipStatus.INVITED:
            record.membership.status = MembershipStatus.INACTIVE


async def change_membership_status(
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    new_status: MembershipStatus,
    actor: SessionIdentity,
    session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        record = await repository.get_membership_by_id(session, tenant_id, membership_id)
        if record is None:
            raise MembershipConflictError("Member was not found")
        if record.user.id == actor.user.id and new_status != MembershipStatus.ACTIVE:
            raise MembershipConflictError("You cannot deactivate your own membership")
        if new_status == MembershipStatus.ACTIVE and record.user.password_hash is None:
            raise MembershipConflictError("This person must accept an invitation first")
        record.membership.status = new_status
        record.membership.failed_sign_in_attempts = 0
        record.membership.locked_until = None
        if new_status == MembershipStatus.INACTIVE:
            await identity_repository.revoke_user_sessions(session, tenant_id, record.user.id, now)
            await session.execute(
                update(InvitationToken)
                .where(
                    InvitationToken.tenant_id == tenant_id,
                    InvitationToken.email == record.user.email,
                    InvitationToken.accepted_at.is_(None),
                    InvitationToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            await _discard_queued_invitation_emails(
                session,
                tenant_id,
                recipient=record.user.email,
            )
