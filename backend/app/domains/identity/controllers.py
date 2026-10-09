import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.core.tenant_resolution import ResolvedTenant
from app.core.urls import tenant_frontend_url
from app.domains.communications.controllers import enqueue_email
from app.domains.communications.schemas import EmailMessage
from app.domains.identity.models import (
    AuthenticationEvent,
    AuthSession,
    MembershipStatus,
    PasswordResetToken,
    TenantSSOConfiguration,
    User,
    WorkspaceSelectionToken,
)
from app.domains.identity.repositories import (
    GlobalSignInUser,
    SessionRecord,
    SQLAlchemyIdentityRepository,
    UserWorkspace,
)
from app.domains.identity.schemas import (
    AuthenticatedTenant,
    AuthenticatedUser,
    CentralSignInResult,
    InvitationAcceptanceCommand,
    InvitationInspectionResult,
    InvitationTokenCommand,
    PasswordResetCommand,
    PasswordResetRequestCommand,
    SessionIdentity,
    SignInCommand,
    SignInResult,
    WorkspaceChoice,
    WorkspaceSelectionCommand,
)
from app.domains.identity.security import (
    authentication_key,
    consume_global_rate_limit,
    consume_rate_limit,
)
from app.domains.identity.services import (
    generate_session_token,
    hash_password,
    hash_session_token,
    password_reset_expiry,
    session_expiry,
    verify_password,
)
from app.domains.tenants.models import Tenant, TenantStatus


class InvalidCredentialsError(Exception):
    pass


class InvalidSessionError(Exception):
    pass


class InvalidWorkspaceSelectionError(Exception):
    pass


class InvalidPasswordResetTokenError(Exception):
    pass


class AuthenticationThrottledError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Authentication requests are temporarily limited")


class InvalidInvitationTokenError(Exception):
    pass


class InvitationPasswordRequiredError(Exception):
    pass


def _invitation_tenant_id(token: str) -> uuid.UUID:
    tenant_id, separator, secret = token.partition(".")
    if not separator or not secret:
        raise InvalidInvitationTokenError
    try:
        return uuid.UUID(tenant_id)
    except ValueError as error:
        raise InvalidInvitationTokenError from error


@dataclass(frozen=True, slots=True)
class ClientContext:
    ip_address: str | None
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    csrf_token: str
    identity: SignInResult
    persistent: bool


@dataclass(frozen=True, slots=True)
class CentralSignInOutcome:
    result: CentralSignInResult
    issued_session: IssuedSession | None = None


repository = SQLAlchemyIdentityRepository()


def _global_user_from_model(user: User) -> GlobalSignInUser:
    return GlobalSignInUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        password_hash=user.password_hash,
        is_platform_admin=user.is_platform_admin,
        failed_sign_in_attempts=user.failed_sign_in_attempts,
        locked_until=user.locked_until,
    )


def _session_identity(
    record: SessionRecord,
    tenant: ResolvedTenant,
    roles: list[str],
) -> SessionIdentity:
    return SessionIdentity(
        user=AuthenticatedUser(
            id=record.user.id,
            email=record.user.email,
            display_name=record.user.display_name,
            is_platform_admin=record.user.is_platform_admin,
        ),
        tenant=AuthenticatedTenant(
            id=tenant.tenant_id,
            slug=tenant.slug,
            name=tenant.name,
        ),
        roles=roles,
        expires_at=record.auth_session.expires_at,
        session_scope=record.auth_session.scope,
    )


def _authentication_event(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    event_type: str,
    outcome: str,
    client: ClientContext,
) -> AuthenticationEvent:
    return AuthenticationEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=event_type,
        outcome=outcome,
        ip_address=client.ip_address,
        user_agent=client.user_agent,
    )


async def sign_in(
    command: SignInCommand,
    tenant: ResolvedTenant,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> IssuedSession:
    normalized_email = str(command.email).strip().casefold()
    raw_token = ""
    csrf_token = ""
    identity_result: SignInResult | None = None
    retry_after_seconds: int | None = None

    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        rate_limit = await consume_rate_limit(
            session,
            tenant_id=tenant.tenant_id,
            action="sign_in",
            key_hash=authentication_key("sign_in", normalized_email, client.ip_address),
            limit=settings.sign_in_rate_limit,
            window_seconds=settings.auth_rate_window_seconds,
            block_seconds=settings.auth_rate_block_seconds,
        )
        if not rate_limit.allowed:
            retry_after_seconds = rate_limit.retry_after_seconds or settings.auth_rate_block_seconds
            session.add(
                _authentication_event(
                    tenant_id=tenant.tenant_id,
                    user_id=None,
                    event_type="sign_in",
                    outcome="throttled",
                    client=client,
                )
            )
        else:
            identity = await repository.get_identity_by_email(
                session,
                tenant.tenant_id,
                normalized_email,
            )
            password_valid = verify_password(
                command.password,
                identity.user.password_hash if identity else None,
            )
            now = datetime.now(UTC)
            membership_active = bool(
                identity and identity.membership.status == MembershipStatus.ACTIVE
            )
            temporarily_locked = bool(
                identity
                and identity.membership.locked_until
                and identity.membership.locked_until > now
            )

            if not identity or not password_valid or not membership_active or temporarily_locked:
                if identity and membership_active and not temporarily_locked:
                    identity.membership.failed_sign_in_attempts += 1
                    if (
                        identity.membership.failed_sign_in_attempts
                        >= settings.account_lockout_attempts
                    ):
                        identity.membership.locked_until = now + timedelta(
                            minutes=settings.account_lockout_minutes
                        )
                session.add(
                    _authentication_event(
                        tenant_id=tenant.tenant_id,
                        user_id=identity.user.id if identity else None,
                        event_type="sign_in",
                        outcome="locked" if temporarily_locked else "failure",
                        client=client,
                    )
                )
            else:
                identity.membership.failed_sign_in_attempts = 0
                identity.membership.locked_until = None
                raw_token = generate_session_token()
                csrf_token = generate_session_token()
                expires_at = session_expiry(
                    remember_me=command.remember_me,
                    hours=settings.session_hours,
                    remembered_days=settings.remembered_session_days,
                )
                auth_session = AuthSession(
                    tenant_id=tenant.tenant_id,
                    user_id=identity.user.id,
                    token_hash=hash_session_token(raw_token),
                    expires_at=expires_at,
                )
                session.add(auth_session)
                session.add(
                    _authentication_event(
                        tenant_id=tenant.tenant_id,
                        user_id=identity.user.id,
                        event_type="sign_in",
                        outcome="success",
                        client=client,
                    )
                )
                roles = await repository.get_role_keys(
                    session,
                    tenant.tenant_id,
                    identity.membership.id,
                )
                identity_result = SignInResult(
                    user=AuthenticatedUser(
                        id=identity.user.id,
                        email=identity.user.email,
                        display_name=identity.user.display_name,
                        is_platform_admin=identity.user.is_platform_admin,
                    ),
                    tenant=AuthenticatedTenant(
                        id=tenant.tenant_id,
                        slug=tenant.slug,
                        name=tenant.name,
                    ),
                    roles=roles,
                    expires_at=expires_at,
                    session_scope="full",
                )

    if retry_after_seconds is not None:
        raise AuthenticationThrottledError(retry_after_seconds)
    if identity_result is None:
        raise InvalidCredentialsError
    return IssuedSession(
        token=raw_token,
        csrf_token=csrf_token,
        identity=identity_result,
        persistent=command.remember_me,
    )


async def _issue_workspace_session(
    session: AsyncSession,
    *,
    user: GlobalSignInUser,
    workspace: UserWorkspace,
    remember_me: bool,
    client: ClientContext,
    settings: Settings,
) -> IssuedSession:
    raw_token = generate_session_token()
    csrf_token = generate_session_token()
    expires_at = session_expiry(
        remember_me=remember_me,
        hours=settings.session_hours,
        remembered_days=settings.remembered_session_days,
    )
    session.add(
        AuthSession(
            tenant_id=workspace.tenant_id,
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=expires_at,
        )
    )
    session.add(
        _authentication_event(
            tenant_id=workspace.tenant_id,
            user_id=user.id,
            event_type="sign_in",
            outcome="success",
            client=client,
        )
    )
    roles = await repository.get_role_keys(
        session,
        workspace.tenant_id,
        workspace.membership_id,
    )
    identity = SignInResult(
        user=AuthenticatedUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_platform_admin=user.is_platform_admin,
        ),
        tenant=AuthenticatedTenant(
            id=workspace.tenant_id,
            slug=workspace.slug,
            name=workspace.name,
        ),
        roles=roles,
        expires_at=expires_at,
        session_scope="full",
    )
    return IssuedSession(
        token=raw_token,
        csrf_token=csrf_token,
        identity=identity,
        persistent=remember_me,
    )


async def central_sign_in(
    command: SignInCommand,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> CentralSignInOutcome:
    normalized_email = str(command.email).strip().casefold()
    retry_after_seconds: int | None = None
    outcome: CentralSignInOutcome | None = None

    async with session.begin():
        rate_limit = await consume_global_rate_limit(
            session,
            action="central_sign_in",
            key_hash=authentication_key("central_sign_in", normalized_email, client.ip_address),
            limit=settings.sign_in_rate_limit,
            window_seconds=settings.auth_rate_window_seconds,
            block_seconds=settings.auth_rate_block_seconds,
        )
        if not rate_limit.allowed:
            retry_after_seconds = rate_limit.retry_after_seconds or settings.auth_rate_block_seconds
        else:
            user = await repository.get_global_sign_in_user(session, normalized_email)
            workspaces = (
                await repository.list_active_user_workspaces(session, user.id) if user else []
            )
            workspaces = [
                workspace
                for workspace in workspaces
                if not await repository.tenant_requires_sso(session, workspace.tenant_id)
            ]
            password_valid = verify_password(command.password, user.password_hash if user else None)
            now = datetime.now(UTC)
            temporarily_locked = bool(user and user.locked_until and user.locked_until > now)

            if not user or not password_valid or not workspaces or temporarily_locked:
                if user and workspaces:
                    await apply_tenant_to_transaction(session, workspaces[0].tenant_id)
                    stored_user = await session.get(User, user.id)
                    if stored_user and not temporarily_locked:
                        stored_user.failed_sign_in_attempts += 1
                        if stored_user.failed_sign_in_attempts >= settings.account_lockout_attempts:
                            stored_user.locked_until = now + timedelta(
                                minutes=settings.account_lockout_minutes
                            )
                    session.add(
                        _authentication_event(
                            tenant_id=workspaces[0].tenant_id,
                            user_id=user.id,
                            event_type="sign_in",
                            outcome="locked" if temporarily_locked else "failure",
                            client=client,
                        )
                    )
            else:
                await apply_tenant_to_transaction(session, workspaces[0].tenant_id)
                stored_user = await session.get(User, user.id)
                if stored_user:
                    stored_user.failed_sign_in_attempts = 0
                    stored_user.locked_until = None

                selected = next(
                    (
                        workspace
                        for workspace in workspaces
                        if workspace.slug == command.preferred_tenant_slug
                    ),
                    None,
                )
                if selected is None and len(workspaces) == 1:
                    selected = workspaces[0]

                if selected is not None:
                    await apply_tenant_to_transaction(session, selected.tenant_id)
                    issued = await _issue_workspace_session(
                        session,
                        user=user,
                        workspace=selected,
                        remember_me=command.remember_me,
                        client=client,
                        settings=settings,
                    )
                    outcome = CentralSignInOutcome(
                        result=CentralSignInResult(
                            selection_required=False,
                            session=issued.identity,
                        ),
                        issued_session=issued,
                    )
                else:
                    await session.execute(
                        update(WorkspaceSelectionToken)
                        .where(
                            WorkspaceSelectionToken.user_id == user.id,
                            WorkspaceSelectionToken.consumed_at.is_(None),
                        )
                        .values(consumed_at=now)
                    )
                    raw_selection_token = generate_session_token()
                    session.add(
                        WorkspaceSelectionToken(
                            user_id=user.id,
                            token_hash=hash_session_token(raw_selection_token),
                            remember_me=command.remember_me,
                            expires_at=now
                            + timedelta(minutes=settings.workspace_selection_minutes),
                        )
                    )
                    outcome = CentralSignInOutcome(
                        result=CentralSignInResult(
                            selection_required=True,
                            selection_token=raw_selection_token,
                            workspaces=[
                                WorkspaceChoice(
                                    id=workspace.tenant_id,
                                    slug=workspace.slug,
                                    name=workspace.name,
                                )
                                for workspace in workspaces
                            ],
                        )
                    )

    if retry_after_seconds is not None:
        raise AuthenticationThrottledError(retry_after_seconds)
    if outcome is None:
        raise InvalidCredentialsError
    return outcome


async def select_workspace(
    command: WorkspaceSelectionCommand,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> CentralSignInOutcome:
    now = datetime.now(UTC)
    outcome: CentralSignInOutcome | None = None
    async with session.begin():
        challenge = await repository.get_workspace_selection_token(
            session,
            hash_session_token(command.selection_token),
            now,
        )
        if challenge is not None:
            workspaces = await repository.list_active_user_workspaces(session, challenge.user_id)
            selected = next(
                (workspace for workspace in workspaces if workspace.tenant_id == command.tenant_id),
                None,
            )
            if selected is not None:
                await apply_tenant_to_transaction(session, selected.tenant_id)
                stored_user = await session.get(User, challenge.user_id)
                if stored_user is not None:
                    challenge.consumed_at = now
                    issued = await _issue_workspace_session(
                        session,
                        user=_global_user_from_model(stored_user),
                        workspace=selected,
                        remember_me=challenge.remember_me,
                        client=client,
                        settings=settings,
                    )
                    outcome = CentralSignInOutcome(
                        result=CentralSignInResult(
                            selection_required=False,
                            session=issued.identity,
                        ),
                        issued_session=issued,
                    )

    if outcome is None:
        raise InvalidWorkspaceSelectionError
    return outcome


async def list_user_workspaces(
    user_id: uuid.UUID, session: AsyncSession
) -> list[WorkspaceChoice]:
    async with session.begin():
        workspaces = await repository.list_active_user_workspaces(session, user_id)
        return [
            WorkspaceChoice(id=item.tenant_id, slug=item.slug, name=item.name)
            for item in workspaces
        ]


async def request_global_password_reset(
    command: PasswordResetRequestCommand,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> None:
    normalized_email = str(command.email).strip().casefold()
    now = datetime.now(UTC)

    async with session.begin():
        rate_limit = await consume_global_rate_limit(
            session,
            action="password_reset",
            key_hash=authentication_key(
                "password_reset", normalized_email, client.ip_address
            ),
            limit=settings.password_reset_rate_limit,
            window_seconds=settings.auth_rate_window_seconds,
            block_seconds=settings.auth_rate_block_seconds,
        )
        if not rate_limit.allowed:
            return

        user = await repository.get_global_sign_in_user(session, normalized_email)
        workspaces = (
            await repository.list_active_user_workspaces(session, user.id) if user else []
        )
        if user is None or not workspaces:
            generate_session_token()
            return

        workspace = workspaces[0]
        await apply_tenant_to_transaction(session, workspace.tenant_id)
        session.add(
            _authentication_event(
                tenant_id=workspace.tenant_id,
                user_id=user.id,
                event_type="password_reset_requested",
                outcome="accepted",
                client=client,
            )
        )
        await repository.expire_password_reset_tokens(
            session, workspace.tenant_id, user.id, now
        )
        raw_token = generate_session_token()
        session.add(
            PasswordResetToken(
                tenant_id=workspace.tenant_id,
                user_id=user.id,
                token_hash=hash_session_token(raw_token),
                expires_at=password_reset_expiry(settings.password_reset_minutes),
            )
        )
        enqueue_email(
            session,
            EmailMessage(
                tenant_id=workspace.tenant_id,
                recipient=user.email,
                template_key="password_reset",
                subject="Reset your TRANSPIRE password",
                template_data={
                    "recipient_name": user.display_name,
                    "tenant_name": workspace.name,
                    "expires_in": f"{settings.password_reset_minutes} minutes",
                    "action_label": "Reset password",
                },
            ),
            settings,
            sensitive_template_data={
                "action_url": tenant_frontend_url(
                    settings,
                    workspace.slug,
                    "/reset-password",
                    query={"token": raw_token},
                )
            },
        )


async def read_session(
    raw_token: str | None,
    tenant: ResolvedTenant,
    session: AsyncSession,
) -> SessionIdentity:
    if not raw_token:
        raise InvalidSessionError

    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        record = await repository.get_session(
            session,
            tenant.tenant_id,
            hash_session_token(raw_token),
            datetime.now(UTC),
        )
        if record is None or record.membership.status != MembershipStatus.ACTIVE:
            raise InvalidSessionError
        roles = await repository.get_role_keys(
            session,
            tenant.tenant_id,
            record.membership.id,
        )
        return _session_identity(record, tenant, roles)


async def sign_out(
    raw_token: str | None,
    tenant: ResolvedTenant,
    client: ClientContext,
    session: AsyncSession,
) -> None:
    if not raw_token:
        return

    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        record = await repository.get_session(
            session,
            tenant.tenant_id,
            hash_session_token(raw_token),
            datetime.now(UTC),
        )
        if record is None:
            return
        record.auth_session.revoked_at = datetime.now(UTC)
        session.add(
            _authentication_event(
                tenant_id=tenant.tenant_id,
                user_id=record.user.id,
                event_type="sign_out",
                outcome="success",
                client=client,
            )
        )


async def request_password_reset(
    command: PasswordResetRequestCommand,
    tenant: ResolvedTenant,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> None:
    normalized_email = str(command.email).strip().casefold()
    now = datetime.now(UTC)

    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        rate_limit = await consume_rate_limit(
            session,
            tenant_id=tenant.tenant_id,
            action="password_reset",
            key_hash=authentication_key(
                "password_reset",
                normalized_email,
                client.ip_address,
            ),
            limit=settings.password_reset_rate_limit,
            window_seconds=settings.auth_rate_window_seconds,
            block_seconds=settings.auth_rate_block_seconds,
        )
        if not rate_limit.allowed:
            session.add(
                _authentication_event(
                    tenant_id=tenant.tenant_id,
                    user_id=None,
                    event_type="password_reset_requested",
                    outcome="throttled",
                    client=client,
                )
            )
            return
        identity = await repository.get_identity_by_email(
            session,
            tenant.tenant_id,
            normalized_email,
        )
        active = bool(identity and identity.membership.status == MembershipStatus.ACTIVE)
        session.add(
            _authentication_event(
                tenant_id=tenant.tenant_id,
                user_id=identity.user.id if identity else None,
                event_type="password_reset_requested",
                outcome="accepted",
                client=client,
            )
        )
        if not identity or not active:
            generate_session_token()
            return

        await repository.expire_password_reset_tokens(
            session,
            tenant.tenant_id,
            identity.user.id,
            now,
        )
        raw_token = generate_session_token()
        session.add(
            PasswordResetToken(
                tenant_id=tenant.tenant_id,
                user_id=identity.user.id,
                token_hash=hash_session_token(raw_token),
                expires_at=password_reset_expiry(settings.password_reset_minutes),
            )
        )
        enqueue_email(
            session,
            EmailMessage(
                tenant_id=tenant.tenant_id,
                recipient=identity.user.email,
                template_key="password_reset",
                subject="Reset your TRANSPIRE password",
                template_data={
                    "recipient_name": identity.user.display_name,
                    "tenant_name": tenant.name,
                    "expires_in": f"{settings.password_reset_minutes} minutes",
                    "action_label": "Reset password",
                },
            ),
            settings,
            sensitive_template_data={
                    "action_url": tenant_frontend_url(
                        settings,
                        tenant.slug,
                        "/reset-password",
                        query={"token": raw_token},
                    )
            },
        )


async def reset_password(
    command: PasswordResetCommand,
    tenant: ResolvedTenant,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    invalid_token = False

    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        record = await repository.get_password_reset_token(
            session,
            tenant.tenant_id,
            hash_session_token(command.token),
            now,
        )
        if record is None or record.membership.status != MembershipStatus.ACTIVE:
            session.add(
                _authentication_event(
                    tenant_id=tenant.tenant_id,
                    user_id=None,
                    event_type="password_reset",
                    outcome="failure",
                    client=client,
                )
            )
            invalid_token = True
        else:
            record.user.password_hash = hash_password(command.new_password)
            record.membership.failed_sign_in_attempts = 0
            record.membership.locked_until = None
            record.reset_token.consumed_at = now
            await repository.revoke_user_sessions(
                session,
                tenant.tenant_id,
                record.user.id,
                now,
            )
            session.add(
                _authentication_event(
                    tenant_id=tenant.tenant_id,
                    user_id=record.user.id,
                    event_type="password_reset",
                    outcome="success",
                    client=client,
                )
            )
            enqueue_email(
                session,
                EmailMessage(
                    tenant_id=tenant.tenant_id,
                    recipient=record.user.email,
                    template_key="account_security",
                    subject="Your TRANSPIRE password was changed",
                    template_data={
                        "recipient_name": record.user.display_name,
                        "tenant_name": tenant.name,
                        "event_description": "Your password was changed",
                        "event_time": now.strftime("%d %B %Y at %H:%M UTC"),
                        "action_url": tenant_frontend_url(
                            settings, tenant.slug, "/sign-in"
                        ),
                        "action_label": "Return to TRANSPIRE",
                    },
                ),
                settings,
            )

    if invalid_token:
        raise InvalidPasswordResetTokenError


async def inspect_invitation(
    command: InvitationTokenCommand,
    settings: Settings,
    session: AsyncSession,
) -> InvitationInspectionResult:
    tenant_id = _invitation_tenant_id(command.token)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise InvalidInvitationTokenError
        record = await repository.get_invitation(
            session,
            tenant_id,
            hash_session_token(command.token),
            datetime.now(UTC),
            for_update=False,
        )
        if record is None:
            raise InvalidInvitationTokenError
        sso_active = bool(
            await session.scalar(
                select(TenantSSOConfiguration.id).where(
                    TenantSSOConfiguration.tenant_id == tenant_id,
                    TenantSSOConfiguration.status == "active",
                )
            )
        )
        return InvitationInspectionResult(
            email=record.user.email,
            display_name=record.user.display_name,
            tenant_name=tenant.name,
            sign_in_url=tenant_frontend_url(settings, tenant.slug, "/sign-in"),
            requires_password=record.user.password_hash is None and not sso_active,
            sso_required=sso_active,
            expires_at=record.invitation.expires_at,
        )


async def accept_invitation(
    command: InvitationAcceptanceCommand,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> None:
    tenant_id = _invitation_tenant_id(command.token)
    retry_after_seconds: int | None = None
    invalid_token = False
    password_required = False
    now = datetime.now(UTC)

    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise InvalidInvitationTokenError
        rate_limit = await consume_rate_limit(
            session,
            tenant_id=tenant_id,
            action="invitation_accept",
            key_hash=authentication_key(
                "invitation_accept",
                hash_session_token(command.token),
                client.ip_address,
            ),
            limit=settings.sign_in_rate_limit,
            window_seconds=settings.auth_rate_window_seconds,
            block_seconds=settings.auth_rate_block_seconds,
        )
        if not rate_limit.allowed:
            retry_after_seconds = rate_limit.retry_after_seconds or settings.auth_rate_block_seconds
        else:
            sso_active = bool(
                await session.scalar(
                    select(TenantSSOConfiguration.id).where(
                        TenantSSOConfiguration.tenant_id == tenant_id,
                        TenantSSOConfiguration.status == "active",
                    )
                )
            )
            record = await repository.get_invitation(
                session,
                tenant_id,
                hash_session_token(command.token),
                now,
                for_update=True,
            )
            if record is None:
                invalid_token = True
                session.add(
                    _authentication_event(
                        tenant_id=tenant_id,
                        user_id=None,
                        event_type="invitation_acceptance",
                        outcome="failure",
                        client=client,
                    )
                )
            elif (
                not sso_active
                and record.user.password_hash is None
                and command.new_password is None
            ):
                password_required = True
            else:
                if record.user.password_hash is None and command.new_password:
                    record.user.password_hash = hash_password(command.new_password)
                record.membership.status = MembershipStatus.ACTIVE
                record.membership.failed_sign_in_attempts = 0
                record.membership.locked_until = None
                record.invitation.accepted_at = now
                session.add(
                    _authentication_event(
                        tenant_id=tenant_id,
                        user_id=record.user.id,
                        event_type="invitation_acceptance",
                        outcome="success",
                        client=client,
                    )
                )
                enqueue_email(
                    session,
                    EmailMessage(
                        tenant_id=tenant_id,
                        recipient=record.user.email,
                        template_key="account_security",
                        subject="Your TRANSPIRE access is active",
                        template_data={
                            "recipient_name": record.user.display_name,
                            "tenant_name": tenant.name,
                            "event_description": "Your invitation was accepted",
                            "event_time": now.strftime("%d %B %Y at %H:%M UTC"),
                            "action_url": tenant_frontend_url(
                                settings, tenant.slug, "/sign-in"
                            ),
                            "action_label": "Sign in to TRANSPIRE",
                        },
                    ),
                    settings,
                )

    if retry_after_seconds is not None:
        raise AuthenticationThrottledError(retry_after_seconds)
    if invalid_token:
        raise InvalidInvitationTokenError
    if password_required:
        raise InvitationPasswordRequiredError
