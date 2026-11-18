import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.core.urls import platform_frontend_url, tenant_frontend_url
from app.domains.audit.controllers import record_audit_event
from app.domains.communications.controllers import enqueue_email
from app.domains.communications.models import EmailDelivery, EmailDeliveryStatus
from app.domains.communications.schemas import EmailMessage
from app.domains.configuration.controllers import (
    create_default_master_data,
    create_default_workflow,
)
from app.domains.ideas.services import create_default_idea_bank_policy
from app.domains.identity.access import (
    ADMIN_ROLE_KEYS,
    ROLES_BY_KEY,
    WORKSPACE_OWNER,
    WORKSPACE_ROLES,
    can_manage_role,
)
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
from app.domains.tenants.reminders import last_sign_ins
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


class RolePermissionError(Exception):
    pass


repository = SQLAlchemyTenantRepository()
identity_repository = SQLAlchemyIdentityRepository()


def _require_manageable(actor_roles: list[str] | None, role_keys: list[str], action: str) -> None:
    """Enforce the role ladder. ``actor_roles=None`` is platform administration."""
    if actor_roles is None:
        return
    for key in role_keys:
        if not can_manage_role(actor_roles, key):
            name = ROLES_BY_KEY[key].name if key in ROLES_BY_KEY else "this role"
            raise RolePermissionError(f"Only a Workspace Owner can {action} a {name}.")


async def _ensure_owner_remains(
    session: AsyncSession, tenant_id: uuid.UUID, membership_id: uuid.UUID
) -> None:
    owners = await repository.lock_active_owner_membership_ids(session, tenant_id)
    if membership_id in owners and len(owners) <= 1:
        raise MembershipConflictError(
            "A workspace must keep at least one active Workspace Owner. "
            "Make someone else an Owner first."
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
    for definition in WORKSPACE_ROLES:
        role = Role(
            tenant_id=tenant_id,
            key=definition.key,
            name=definition.name,
            permissions=list(definition.permissions),
            is_system=True,
        )
        session.add(role)
        roles[definition.key] = role
    await session.flush()
    return roles


async def _queue_invitation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    tenant_name: str,
    email: str,
    display_name: str,
    inviter: SessionIdentity | None,
    role: Role,
    settings: Settings,
    provisioned_by: str = "manual",
) -> InvitationResult:
    """Queue an invitation. ``inviter`` is None for automatic HR directory provisioning."""
    user_id = await repository.ensure_invited_user(session, email, display_name)
    membership = await repository.get_membership(session, tenant_id, user_id)
    if membership and membership.status == MembershipStatus.ACTIVE:
        raise InvitationConflictError("This person is already an active member")
    if membership is None:
        membership = Membership(
            tenant_id=tenant_id,
            user_id=user_id,
            status=MembershipStatus.INVITED,
            provisioned_by=provisioned_by,
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
        invited_by_user_id=inviter.user.id if inviter else None,
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
            subject=f"You're invited to join {tenant_name} on TRANSPIRE",
            template_data={
                "recipient_name": display_name,
                "tenant_name": tenant_name,
                "inviter_name": inviter.user.display_name if inviter else f"{tenant_name} HR",
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
            role_key=row["role_key"] or WORKSPACE_OWNER,
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
            role=roles[WORKSPACE_OWNER],
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
        if role is None or role.key not in ROLES_BY_KEY:
            raise RoleNotFoundError
        _require_manageable(inviter.roles, [role.key], "invite")
        user_id = await repository.ensure_invited_user(session, email, command.display_name)
        existing = await repository.get_membership(session, tenant_id, user_id)
        if existing is not None:
            _require_manageable(
                inviter.roles,
                await identity_repository.get_role_keys(session, tenant_id, existing.id),
                "re-invite",
            )
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
    actor: SessionIdentity | None = None,
) -> list[TenantMemberSummary]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        members = await repository.list_members(session, tenant_id)
        sign_ins = await last_sign_ins(session, tenant_id, [record.user.id for record in members])
        summaries = []
        for record in members:
            role_keys = await identity_repository.get_role_keys(
                session, tenant_id, record.membership.id
            )
            summaries.append(
                TenantMemberSummary(
                    id=record.membership.id,
                    email=record.user.email,
                    display_name=record.user.display_name,
                    status=record.membership.status.value,
                    roles=role_keys,
                    can_manage=actor is not None
                    and record.user.id != actor.user.id
                    and all(can_manage_role(actor.roles, key) for key in role_keys),
                    last_signed_in_at=sign_ins.get(record.user.id),
                )
            )
        return summaries


async def list_roles(
    tenant_id: uuid.UUID,
    session: AsyncSession,
    actor: SessionIdentity,
) -> list[TenantRoleSummary]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        stored = {role.key for role in await repository.list_roles(session, tenant_id)}
        return [
            TenantRoleSummary(
                key=definition.key,
                name=definition.name,
                description=definition.description,
                rank=definition.rank,
                assignable=can_manage_role(actor.roles, definition.key),
            )
            for definition in WORKSPACE_ROLES
            if definition.key in stored
        ]


ROLE_MEANING = {
    "viewer": "You can read ideas and projects in this workspace, but not create or change them.",
    "idea_submitter": "You can submit ideas, approve when assigned, and work on your projects.",
    "tenant_admin": (
        "You can manage configuration, approval workflows, and Viewers and Contributors."
    ),
    "workspace_owner": (
        "You have full control, including roles, sign-in and security settings."
    ),
}


async def _email_role_change(
    session: AsyncSession,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    actor: SessionIdentity,
    subject_user: object,
    subject_membership_id: uuid.UUID,
    previous: str,
    new_role_key: str,
) -> None:
    """Security notices: always sent, regardless of email preferences."""
    tenant = await repository.get_tenant(session, tenant_id)
    if tenant is None:
        return
    new_name = ROLES_BY_KEY[new_role_key].name
    people_url = tenant_frontend_url(settings, tenant.slug, "/admin/people")
    common = {
        "tenant_name": tenant.name,
        "previous_role": previous,
        "new_role": new_name,
        "changed_by": actor.user.display_name,
    }
    enqueue_email(
        session,
        EmailMessage(
            tenant_id=tenant_id,
            recipient=subject_user.email,  # type: ignore[attr-defined]
            template_key="role_changed",
            subject=f"Your access to {tenant.name} changed to {new_name}",
            template_data={
                **common,
                "recipient_name": subject_user.display_name,  # type: ignore[attr-defined]
                "role_meaning": ROLE_MEANING[new_role_key],
                "action_url": tenant_frontend_url(settings, tenant.slug, "/home"),
                "action_label": "Open TRANSPIRE",
            },
        ),
        settings,
    )
    if new_role_key not in ADMIN_ROLE_KEYS:
        return
    owners = await repository.lock_active_owner_membership_ids(session, tenant_id)
    for owner_id in owners - {subject_membership_id}:
        owner = await repository.get_membership_by_id(session, tenant_id, owner_id)
        if owner is None or owner.user.id == actor.user.id:
            continue
        enqueue_email(
            session,
            EmailMessage(
                tenant_id=tenant_id,
                recipient=owner.user.email,
                template_key="privileged_role_granted",
                subject=f"{subject_user.display_name} is now a {new_name} in {tenant.name}",  # type: ignore[attr-defined]
                template_data={
                    **common,
                    "recipient_name": owner.user.display_name,
                    "member_name": subject_user.display_name,  # type: ignore[attr-defined]
                    "member_email": subject_user.email,  # type: ignore[attr-defined]
                    "action_url": people_url,
                    "action_label": "Review people",
                },
            ),
            settings,
        )


async def change_member_role(
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    role_key: str,
    actor: SessionIdentity,
    session: AsyncSession,
    settings: Settings | None = None,
) -> TenantMemberSummary:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        record = await repository.get_membership_by_id(session, tenant_id, membership_id)
        if record is None:
            raise MembershipConflictError("Member was not found")
        if record.user.id == actor.user.id:
            raise MembershipConflictError("You cannot change your own role")
        role = await repository.get_role(session, tenant_id, role_key)
        if role is None or role.key not in ROLES_BY_KEY:
            raise RoleNotFoundError
        current = await identity_repository.get_role_keys(session, tenant_id, membership_id)
        _require_manageable(actor.roles, current, "change the role of")
        _require_manageable(actor.roles, [role.key], "assign the role of")
        if current == [role.key]:
            raise MembershipConflictError(f"This person is already a {role.name}")
        if role.key != WORKSPACE_OWNER:
            await _ensure_owner_remains(session, tenant_id, membership_id)
        await session.execute(
            delete(membership_roles).where(membership_roles.c.membership_id == membership_id)
        )
        await session.execute(
            insert(membership_roles).values(membership_id=membership_id, role_id=role.id)
        )
        previous = ", ".join(ROLES_BY_KEY[key].name for key in current if key in ROLES_BY_KEY)
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor.user.id,
            subject_user_id=record.user.id,
            event_type="member.role_changed",
            entity_type="membership",
            entity_id=membership_id,
            entity_reference=record.user.email,
            summary=(
                f"{actor.user.display_name} changed {record.user.display_name}'s role "
                f"from {previous or 'no role'} to {role.name}"
            ),
            details={"from": current, "to": role.key},
        )
        if settings is not None:
            await _email_role_change(
                session,
                settings,
                tenant_id=tenant_id,
                actor=actor,
                subject_user=record.user,
                subject_membership_id=membership_id,
                previous=previous or "no role",
                new_role_key=role.key,
            )
        return TenantMemberSummary(
            id=membership_id,
            email=record.user.email,
            display_name=record.user.display_name,
            status=record.membership.status.value,
            roles=[role.key],
            can_manage=can_manage_role(actor.roles, role.key),
        )


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
    *,
    enforce_role_ladder: bool = True,
) -> InvitationResult:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        record = await repository.get_invitation(session, tenant_id, invitation_id)
        if record is None:
            raise InvitationNotFoundError
        _require_manageable(
            inviter.roles if enforce_role_ladder else None, [record.role.key], "re-invite"
        )
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
    actor_roles: list[str] | None = None,
) -> None:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        record = await repository.get_invitation(session, tenant_id, invitation_id)
        if record is None:
            raise InvitationNotFoundError
        _require_manageable(actor_roles, [record.role.key], "revoke the invitation of")
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
    *,
    enforce_role_ladder: bool = True,
) -> None:
    now = datetime.now(UTC)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        record = await repository.get_membership_by_id(session, tenant_id, membership_id)
        if record is None:
            raise MembershipConflictError("Member was not found")
        if record.user.id == actor.user.id and new_status != MembershipStatus.ACTIVE:
            raise MembershipConflictError("You cannot deactivate your own membership")
        if enforce_role_ladder:
            _require_manageable(
                actor.roles,
                await identity_repository.get_role_keys(session, tenant_id, membership_id),
                "change access for",
            )
            if new_status != MembershipStatus.ACTIVE:
                await _ensure_owner_remains(session, tenant_id, membership_id)
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
