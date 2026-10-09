import base64
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.core.tenant_resolution import ResolvedTenant
from app.core.urls import tenant_frontend_url
from app.domains.communications.controllers import enqueue_email
from app.domains.communications.models import EmailDelivery
from app.domains.communications.schemas import EmailMessage
from app.domains.identity.controllers import (
    ClientContext,
    IssuedSession,
    _issue_workspace_session,
)
from app.domains.identity.models import (
    AuthSession,
    ExternalIdentity,
    GlobalOIDCLoginState,
    Membership,
    MembershipStatus,
    OIDCLoginState,
    Role,
    SSORecoveryToken,
    SSOWorkspaceSelectionToken,
    TenantSSOConfiguration,
    User,
    membership_roles,
)
from app.domains.identity.repositories import GlobalSignInUser, UserWorkspace
from app.domains.identity.schemas import (
    AuthenticatedTenant,
    AuthenticatedUser,
    SessionIdentity,
    SSOActivationResult,
    SSOConfigurationCommand,
    SSOConfigurationResult,
    SSOReadinessMember,
    SSORecoveryCommand,
    SSORecoveryResult,
    WorkspaceChoice,
)
from app.domains.identity.services import generate_session_token, hash_session_token


class SSOConfigurationError(Exception):
    pass


class SSOAuthenticationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SSOCallbackOutcome:
    redirect_url: str
    issued_session: IssuedSession | None = None
    selection_token: str | None = None


@dataclass(frozen=True, slots=True)
class SSOWorkspaceCandidate:
    tenant_id: uuid.UUID
    slug: str
    name: str
    user_id: uuid.UUID
    membership_id: uuid.UUID


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode_segment(value: str) -> dict[str, object]:
    padded = value + "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def _credentials_ready(settings: Settings) -> bool:
    return bool(settings.entra_client_id and settings.entra_client_secret.get_secret_value())


def _global_callback(settings: Settings) -> str:
    return f"{settings.public_api_url.rstrip('/')}/auth/sso/global/callback"


async def begin_global_sso(settings: Settings, session: AsyncSession, *, remember_me: bool) -> str:
    if not _credentials_ready(settings):
        raise SSOConfigurationError("Microsoft SSO is not available on this platform.")
    state = generate_session_token()
    nonce = generate_session_token()
    verifier = _base64url(secrets.token_bytes(64))
    async with session.begin():
        session.add(
            GlobalOIDCLoginState(
                state_hash=_sha256(state),
                nonce_hash=_sha256(nonce),
                code_verifier=verifier,
                remember_me=remember_me,
                expires_at=datetime.now(UTC) + timedelta(minutes=settings.oidc_state_minutes),
            )
        )
    query = urlencode(
        {
            "client_id": settings.entra_client_id,
            "response_type": "code",
            "redirect_uri": _global_callback(settings),
            "response_mode": "query",
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": _base64url(hashlib.sha256(verifier.encode()).digest()),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return f"https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?{query}"


async def _configuration(
    session: AsyncSession, tenant_id: uuid.UUID, *, for_update: bool = False
) -> TenantSSOConfiguration | None:
    statement = select(TenantSSOConfiguration).where(
        TenantSSOConfiguration.tenant_id == tenant_id
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def tenant_requires_sso(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        config = await _configuration(session, tenant_id)
        return bool(config and config.status == "active")


async def _readiness_members(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[SSOReadinessMember]:
    rows = (
        await session.execute(
            select(Membership, User, ExternalIdentity.id)
            .join(User, User.id == Membership.user_id)
            .outerjoin(
                ExternalIdentity,
                (ExternalIdentity.tenant_id == tenant_id)
                & (ExternalIdentity.user_id == User.id)
                & (ExternalIdentity.provider == "microsoft_entra"),
            )
            .where(
                Membership.tenant_id == tenant_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
            .order_by(func.lower(User.display_name), User.id)
        )
    ).all()
    return [
        SSOReadinessMember(
            membership_id=membership.id,
            email=user.email,
            display_name=user.display_name,
            status=membership.status.value,
            linked=external_id is not None,
            ready=bool(user.email and "@" in user.email),
            reason=None if user.email and "@" in user.email else "A valid work email is required.",
        )
        for membership, user, external_id in rows
    ]


async def get_sso_configuration(
    tenant_id: uuid.UUID, settings: Settings, session: AsyncSession
) -> SSOConfigurationResult:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        config = await _configuration(session, tenant_id)
        members = await _readiness_members(session, tenant_id)
        notification_count = 0
        if config and config.activation_id:
            notification_count = int(
                await session.scalar(
                    select(func.count(EmailDelivery.id)).where(
                        EmailDelivery.tenant_id == tenant_id,
                        EmailDelivery.correlation_id == config.activation_id,
                        EmailDelivery.template_key == "sso_migration",
                    )
                )
                or 0
            )
        return SSOConfigurationResult(
            status=config.status if config else "not_configured",
            entra_directory_id=config.entra_directory_id if config else None,
            client_id_configured=_credentials_ready(settings),
            validated_at=config.validated_at if config else None,
            activated_at=config.activated_at if config else None,
            active_user_count=len(members),
            ready_user_count=sum(member.ready for member in members),
            notification_count=notification_count,
            members=members,
        )


async def configure_sso(
    command: SSOConfigurationCommand,
    identity: SessionIdentity,
    tenant_id: uuid.UUID,
    settings: Settings,
    session: AsyncSession,
) -> SSOConfigurationResult:
    if not _credentials_ready(settings):
        raise SSOConfigurationError(
            "The platform Microsoft application credentials have not been configured."
        )
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        config = await _configuration(session, tenant_id, for_update=True)
        directory_id = str(command.entra_directory_id)
        if config and config.status == "active" and config.entra_directory_id != directory_id:
            raise SSOConfigurationError(
                "Use platform-controlled recovery to change the directory after activation."
            )
        if config is None:
            config = TenantSSOConfiguration(
                tenant_id=tenant_id,
                entra_directory_id=directory_id,
                status="configured",
            )
            session.add(config)
        elif config.entra_directory_id != directory_id:
            config.entra_directory_id = directory_id
            config.status = "configured"
            config.validated_at = None
            config.validated_by_user_id = None
    return await get_sso_configuration(tenant_id, settings, session)


async def begin_sso(
    tenant: ResolvedTenant,
    settings: Settings,
    session: AsyncSession,
    *,
    purpose: str,
    initiated_by_user_id: uuid.UUID | None = None,
    remember_me: bool = False,
) -> str:
    if not _credentials_ready(settings):
        raise SSOConfigurationError("Microsoft SSO is not available on this platform.")
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        config = await _configuration(session, tenant.tenant_id)
        if config is None or (purpose == "sign_in" and config.status != "active"):
            raise SSOConfigurationError("Microsoft SSO is not active for this organisation.")
        if purpose == "validate" and initiated_by_user_id is None:
            raise SSOConfigurationError("An administrator session is required to validate SSO.")
        state = generate_session_token()
        nonce = generate_session_token()
        verifier = _base64url(secrets.token_bytes(64))
        session.add(
            OIDCLoginState(
                tenant_id=tenant.tenant_id,
                state_hash=_sha256(state),
                nonce_hash=_sha256(nonce),
                code_verifier=verifier,
                purpose=purpose,
                initiated_by_user_id=initiated_by_user_id,
                remember_me=remember_me,
                expires_at=datetime.now(UTC) + timedelta(minutes=settings.oidc_state_minutes),
            )
        )
        directory_id = config.entra_directory_id
    callback = f"{settings.public_api_url.rstrip('/')}/t/{tenant.slug}/auth/sso/callback"
    query = urlencode(
        {
            "client_id": settings.entra_client_id,
            "response_type": "code",
            "redirect_uri": callback,
            "response_mode": "query",
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": _base64url(hashlib.sha256(verifier.encode()).digest()),
            "code_challenge_method": "S256",
        }
    )
    return f"https://login.microsoftonline.com/{directory_id}/oauth2/v2.0/authorize?{query}"


async def _exchange_and_validate(
    *,
    code: str,
    state: OIDCLoginState,
    tenant: ResolvedTenant,
    directory_id: str,
    settings: Settings,
) -> dict[str, object]:
    callback = f"{settings.public_api_url.rstrip('/')}/t/{tenant.slug}/auth/sso/callback"
    token_url = f"https://login.microsoftonline.com/{directory_id}/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            token_url,
            data={
                "client_id": settings.entra_client_id,
                "client_secret": settings.entra_client_secret.get_secret_value(),
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback,
                "code_verifier": state.code_verifier,
            },
        )
        if token_response.status_code != 200:
            raise SSOAuthenticationError("Microsoft could not complete this sign-in.")
        id_token = str(token_response.json().get("id_token", ""))
        parts = id_token.split(".")
        if len(parts) != 3:
            raise SSOAuthenticationError("Microsoft returned an invalid identity token.")
        header = _decode_segment(parts[0])
        claims = _decode_segment(parts[1])
        jwks_response = await client.get(
            f"https://login.microsoftonline.com/{directory_id}/discovery/v2.0/keys"
        )
        jwks_response.raise_for_status()
    key = next(
        (item for item in jwks_response.json().get("keys", []) if item.get("kid") == header.get("kid")),
        None,
    )
    if not key or header.get("alg") != "RS256":
        raise SSOAuthenticationError("Microsoft signing keys could not be verified.")
    public_key = rsa.RSAPublicNumbers(
        int.from_bytes(base64.urlsafe_b64decode(str(key["e"]) + "=" * (-len(str(key["e"])) % 4)), "big"),
        int.from_bytes(base64.urlsafe_b64decode(str(key["n"]) + "=" * (-len(str(key["n"])) % 4)), "big"),
    ).public_key()
    try:
        public_key.verify(
            base64.urlsafe_b64decode(parts[2] + "=" * (-len(parts[2]) % 4)),
            f"{parts[0]}.{parts[1]}".encode(),
            padding.PKCS1v15(),
            SHA256(),
        )
    except Exception as error:
        raise SSOAuthenticationError("Microsoft identity token verification failed.") from error
    now = int(datetime.now(UTC).timestamp())
    expected_issuer = f"https://login.microsoftonline.com/{directory_id}/v2.0"
    audience = claims.get("aud")
    if not (
        claims.get("iss") == expected_issuer
        and claims.get("tid") == directory_id
        and audience == settings.entra_client_id
        and int(claims.get("exp", 0)) > now
        and int(claims.get("nbf", 0)) <= now
        and _sha256(str(claims.get("nonce", ""))) == state.nonce_hash
    ):
        raise SSOAuthenticationError("Microsoft identity claims did not match this organisation.")
    return claims


async def complete_sso(
    *,
    code: str,
    raw_state: str,
    tenant: ResolvedTenant,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> SSOCallbackOutcome:
    now = datetime.now(UTC)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        login_state = await session.scalar(
            select(OIDCLoginState)
            .where(
                OIDCLoginState.tenant_id == tenant.tenant_id,
                OIDCLoginState.state_hash == _sha256(raw_state),
                OIDCLoginState.consumed_at.is_(None),
                OIDCLoginState.expires_at > now,
            )
            .with_for_update()
        )
        config = await _configuration(session, tenant.tenant_id)
        if login_state is None or config is None:
            raise SSOAuthenticationError("This Microsoft sign-in request has expired.")
        login_state.consumed_at = now
        directory_id = config.entra_directory_id
    claims = await _exchange_and_validate(
        code=code,
        state=login_state,
        tenant=tenant,
        directory_id=directory_id,
        settings=settings,
    )
    subject = str(claims.get("oid") or claims.get("sub") or "")
    email = str(claims.get("preferred_username") or claims.get("email") or "").strip().casefold()
    if not subject or not email:
        raise SSOAuthenticationError("Microsoft did not provide a usable work identity.")
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        linked = await session.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.provider == "microsoft_entra",
                ExternalIdentity.provider_tenant_id == directory_id,
                ExternalIdentity.subject == subject,
            )
        )
        if linked:
            user = await session.get(User, linked.user_id)
            membership = await session.scalar(
                select(Membership).where(
                    Membership.tenant_id == tenant.tenant_id,
                    Membership.user_id == linked.user_id,
                    Membership.status == MembershipStatus.ACTIVE,
                )
            )
        else:
            row = (
                await session.execute(
                    select(User, Membership)
                    .join(Membership, Membership.user_id == User.id)
                    .where(
                        Membership.tenant_id == tenant.tenant_id,
                        Membership.status == MembershipStatus.ACTIVE,
                        func.lower(User.email) == email,
                    )
                )
            ).one_or_none()
            user, membership = row if row else (None, None)
            if user and membership:
                session.add(
                    ExternalIdentity(
                        tenant_id=tenant.tenant_id,
                        user_id=user.id,
                        provider_tenant_id=directory_id,
                        subject=subject,
                        linked_email=email,
                    )
                )
        if user is None or membership is None:
            raise SSOAuthenticationError(
                "Your Microsoft account is not linked to an active membership in this organisation."
            )
        roles = list(
            await session.scalars(
                select(Role.key)
                .join(membership_roles, membership_roles.c.role_id == Role.id)
                .where(membership_roles.c.membership_id == membership.id)
            )
        )
        if login_state.purpose == "validate":
            if user.id != login_state.initiated_by_user_id or "tenant_admin" not in roles:
                raise SSOAuthenticationError("The validating Microsoft account must match the tenant administrator.")
            config = await _configuration(session, tenant.tenant_id, for_update=True)
            if config is None:
                raise SSOAuthenticationError("The SSO configuration no longer exists.")
            config.status = "validated"
            config.validated_at = now
            config.validated_by_user_id = user.id
            return SSOCallbackOutcome(
                redirect_url=tenant_frontend_url(settings, tenant.slug, "/admin/configuration?sso=validated")
            )
        if config is None or config.status != "active":
            raise SSOAuthenticationError("Microsoft SSO is not active for this organisation.")
        issued = await _issue_workspace_session(
            session,
            user=GlobalSignInUser(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                password_hash=user.password_hash,
                is_platform_admin=user.is_platform_admin,
                failed_sign_in_attempts=user.failed_sign_in_attempts,
                locked_until=user.locked_until,
            ),
            workspace=UserWorkspace(
                membership_id=membership.id,
                tenant_id=tenant.tenant_id,
                slug=tenant.slug,
                name=tenant.name,
            ),
            remember_me=login_state.remember_me,
            client=client,
            settings=settings,
        )
        return SSOCallbackOutcome(
            redirect_url=tenant_frontend_url(settings, tenant.slug, "/home"),
            issued_session=issued,
        )


async def _exchange_global_code(
    *,
    code: str,
    state: GlobalOIDCLoginState,
    settings: Settings,
) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            "https://login.microsoftonline.com/organizations/oauth2/v2.0/token",
            data={
                "client_id": settings.entra_client_id,
                "client_secret": settings.entra_client_secret.get_secret_value(),
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _global_callback(settings),
                "code_verifier": state.code_verifier,
            },
        )
        if token_response.status_code != 200:
            raise SSOAuthenticationError("Microsoft could not complete this sign-in.")
        id_token = str(token_response.json().get("id_token", ""))
        parts = id_token.split(".")
        if len(parts) != 3:
            raise SSOAuthenticationError("Microsoft returned an invalid identity token.")
        header = _decode_segment(parts[0])
        claims = _decode_segment(parts[1])
        directory_id = str(claims.get("tid", ""))
        try:
            directory_id = str(uuid.UUID(directory_id))
        except ValueError as error:
            raise SSOAuthenticationError("Microsoft returned an invalid directory identity.") from error
        jwks_response = await client.get(
            "https://login.microsoftonline.com/organizations/discovery/v2.0/keys"
        )
        jwks_response.raise_for_status()
    key = next(
        (item for item in jwks_response.json().get("keys", []) if item.get("kid") == header.get("kid")),
        None,
    )
    if not key or header.get("alg") != "RS256":
        raise SSOAuthenticationError("Microsoft signing keys could not be verified.")
    public_key = rsa.RSAPublicNumbers(
        int.from_bytes(base64.urlsafe_b64decode(str(key["e"]) + "=" * (-len(str(key["e"])) % 4)), "big"),
        int.from_bytes(base64.urlsafe_b64decode(str(key["n"]) + "=" * (-len(str(key["n"])) % 4)), "big"),
    ).public_key()
    try:
        public_key.verify(
            base64.urlsafe_b64decode(parts[2] + "=" * (-len(parts[2]) % 4)),
            f"{parts[0]}.{parts[1]}".encode(),
            padding.PKCS1v15(),
            SHA256(),
        )
    except Exception as error:
        raise SSOAuthenticationError("Microsoft identity token verification failed.") from error
    now = int(datetime.now(UTC).timestamp())
    if not (
        claims.get("iss") == f"https://login.microsoftonline.com/{directory_id}/v2.0"
        and claims.get("aud") == settings.entra_client_id
        and int(claims.get("exp", 0)) > now
        and int(claims.get("nbf", 0)) <= now
        and _sha256(str(claims.get("nonce", ""))) == state.nonce_hash
    ):
        raise SSOAuthenticationError("Microsoft identity claims did not match this platform.")
    claims["tid"] = directory_id
    return claims


async def _global_sso_candidates(
    session: AsyncSession, *, directory_id: str, subject: str, email: str
) -> list[SSOWorkspaceCandidate]:
    rows = (
        await session.execute(
            text("SELECT * FROM resolve_active_sso_workspaces(:directory_id, :subject, :email)"),
            {"directory_id": directory_id, "subject": subject, "email": email},
        )
    ).mappings().all()
    return [
        SSOWorkspaceCandidate(
            tenant_id=row["tenant_id"],
            slug=row["slug"],
            name=row["name"],
            user_id=row["user_id"],
            membership_id=row["membership_id"],
        )
        for row in rows
    ]


async def _issue_global_sso_session(
    session: AsyncSession,
    *,
    candidate: SSOWorkspaceCandidate,
    directory_id: str,
    subject: str,
    email: str,
    remember_me: bool,
    client: ClientContext,
    settings: Settings,
) -> IssuedSession:
    await apply_tenant_to_transaction(session, candidate.tenant_id)
    config = await _configuration(session, candidate.tenant_id)
    membership = await session.get(Membership, candidate.membership_id)
    user = await session.get(User, candidate.user_id)
    if (
        config is None
        or config.status != "active"
        or config.entra_directory_id != directory_id
        or membership is None
        or membership.status != MembershipStatus.ACTIVE
        or user is None
    ):
        raise SSOAuthenticationError("This TRANSPIRE workspace is no longer available.")
    linked = await session.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.tenant_id == candidate.tenant_id,
            ExternalIdentity.provider == "microsoft_entra",
            ExternalIdentity.provider_tenant_id == directory_id,
            ExternalIdentity.subject == subject,
        )
    )
    existing_user_link = await session.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.tenant_id == candidate.tenant_id,
            ExternalIdentity.user_id == candidate.user_id,
            ExternalIdentity.provider == "microsoft_entra",
        )
    )
    if linked and linked.user_id != candidate.user_id:
        raise SSOAuthenticationError("This Microsoft identity is linked to another account.")
    if existing_user_link and existing_user_link.subject != subject:
        raise SSOAuthenticationError("This account is linked to another Microsoft identity.")
    if linked is None and existing_user_link is None:
        session.add(
            ExternalIdentity(
                tenant_id=candidate.tenant_id,
                user_id=candidate.user_id,
                provider_tenant_id=directory_id,
                subject=subject,
                linked_email=email,
            )
        )
    return await _issue_workspace_session(
        session,
        user=GlobalSignInUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            password_hash=user.password_hash,
            is_platform_admin=user.is_platform_admin,
            failed_sign_in_attempts=user.failed_sign_in_attempts,
            locked_until=user.locked_until,
        ),
        workspace=UserWorkspace(
            membership_id=membership.id,
            tenant_id=candidate.tenant_id,
            slug=candidate.slug,
            name=candidate.name,
        ),
        remember_me=remember_me,
        client=client,
        settings=settings,
    )


async def complete_global_sso(
    *,
    code: str,
    raw_state: str,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> SSOCallbackOutcome:
    now = datetime.now(UTC)
    async with session.begin():
        login_state = await session.scalar(
            select(GlobalOIDCLoginState)
            .where(
                GlobalOIDCLoginState.state_hash == _sha256(raw_state),
                GlobalOIDCLoginState.consumed_at.is_(None),
                GlobalOIDCLoginState.expires_at > now,
            )
            .with_for_update()
        )
        if login_state is None:
            raise SSOAuthenticationError("This Microsoft sign-in request has expired.")
        login_state.consumed_at = now
        remember_me = login_state.remember_me
        state_copy = GlobalOIDCLoginState(
            state_hash=login_state.state_hash,
            nonce_hash=login_state.nonce_hash,
            code_verifier=login_state.code_verifier,
            remember_me=login_state.remember_me,
            expires_at=login_state.expires_at,
        )
    claims = await _exchange_global_code(code=code, state=state_copy, settings=settings)
    directory_id = str(claims.get("tid", ""))
    subject = str(claims.get("oid") or claims.get("sub") or "")
    email = str(claims.get("preferred_username") or claims.get("email") or "").strip().casefold()
    if not subject or not email:
        raise SSOAuthenticationError("Microsoft did not provide a usable work identity.")
    async with session.begin():
        candidates = await _global_sso_candidates(
            session, directory_id=directory_id, subject=subject, email=email
        )
    if not candidates or len({candidate.user_id for candidate in candidates}) != 1:
        raise SSOAuthenticationError(
            "This Microsoft account is not linked to an active TRANSPIRE workspace."
        )
    if len(candidates) == 1:
        async with session.begin():
            issued = await _issue_global_sso_session(
                session,
                candidate=candidates[0],
                directory_id=directory_id,
                subject=subject,
                email=email,
                remember_me=remember_me,
                client=client,
                settings=settings,
            )
        return SSOCallbackOutcome(
            redirect_url=tenant_frontend_url(settings, candidates[0].slug, "/home"),
            issued_session=issued,
        )
    raw_token = generate_session_token()
    async with session.begin():
        session.add(
            SSOWorkspaceSelectionToken(
                user_id=candidates[0].user_id,
                provider_tenant_id=directory_id,
                subject=subject,
                linked_email=email,
                allowed_tenant_ids=[str(candidate.tenant_id) for candidate in candidates],
                token_hash=hash_session_token(raw_token),
                remember_me=remember_me,
                expires_at=now + timedelta(minutes=settings.workspace_selection_minutes),
            )
        )
    return SSOCallbackOutcome(
        redirect_url=f"{settings.public_app_url.rstrip('/')}/sign-in?sso_select=1",
        selection_token=raw_token,
    )


async def list_sso_workspace_choices(
    raw_token: str | None, session: AsyncSession
) -> list[WorkspaceChoice]:
    if not raw_token:
        raise SSOAuthenticationError("The Microsoft workspace selection has expired.")
    async with session.begin():
        token = await session.scalar(
            select(SSOWorkspaceSelectionToken).where(
                SSOWorkspaceSelectionToken.token_hash == hash_session_token(raw_token),
                SSOWorkspaceSelectionToken.consumed_at.is_(None),
                SSOWorkspaceSelectionToken.expires_at > datetime.now(UTC),
            )
        )
        if token is None:
            raise SSOAuthenticationError("The Microsoft workspace selection has expired.")
        candidates = await _global_sso_candidates(
            session,
            directory_id=token.provider_tenant_id,
            subject=token.subject,
            email=token.linked_email,
        )
        allowed = set(token.allowed_tenant_ids)
        return [
            WorkspaceChoice(id=item.tenant_id, slug=item.slug, name=item.name)
            for item in candidates
            if str(item.tenant_id) in allowed and item.user_id == token.user_id
        ]


async def select_sso_workspace(
    *,
    raw_token: str | None,
    tenant_id: uuid.UUID,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> IssuedSession:
    if not raw_token:
        raise SSOAuthenticationError("The Microsoft workspace selection has expired.")
    async with session.begin():
        token = await session.scalar(
            select(SSOWorkspaceSelectionToken)
            .where(
                SSOWorkspaceSelectionToken.token_hash == hash_session_token(raw_token),
                SSOWorkspaceSelectionToken.consumed_at.is_(None),
                SSOWorkspaceSelectionToken.expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
        if token is None or str(tenant_id) not in set(token.allowed_tenant_ids):
            raise SSOAuthenticationError("The Microsoft workspace selection has expired.")
        candidates = await _global_sso_candidates(
            session,
            directory_id=token.provider_tenant_id,
            subject=token.subject,
            email=token.linked_email,
        )
        candidate = next(
            (
                item
                for item in candidates
                if item.tenant_id == tenant_id and item.user_id == token.user_id
            ),
            None,
        )
        if candidate is None:
            raise SSOAuthenticationError("This TRANSPIRE workspace is no longer available.")
        token.consumed_at = datetime.now(UTC)
        return await _issue_global_sso_session(
            session,
            candidate=candidate,
            directory_id=token.provider_tenant_id,
            subject=token.subject,
            email=token.linked_email,
            remember_me=token.remember_me,
            client=client,
            settings=settings,
        )


async def activate_sso(
    identity: SessionIdentity,
    tenant: ResolvedTenant,
    settings: Settings,
    session: AsyncSession,
) -> SSOActivationResult:
    now = datetime.now(UTC)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        config = await _configuration(session, tenant.tenant_id, for_update=True)
        if config is None or config.validated_at is None:
            raise SSOConfigurationError("Complete a successful administrator SSO test first.")
        members = await _readiness_members(session, tenant.tenant_id)
        if not members or any(not member.ready for member in members):
            raise SSOConfigurationError("Resolve every active member marked Action required first.")
        if config.status != "active":
            activation_id = uuid.uuid4()
            config.status = "active"
            config.activated_at = now
            config.activated_by_user_id = identity.user.id
            config.activation_id = activation_id
            rows = (
                await session.execute(
                    select(User)
                    .join(Membership, Membership.user_id == User.id)
                    .where(
                        Membership.tenant_id == tenant.tenant_id,
                        Membership.status == MembershipStatus.ACTIVE,
                    )
                )
            ).scalars().all()
            for user in rows:
                enqueue_email(
                    session,
                    EmailMessage(
                        tenant_id=tenant.tenant_id,
                        recipient=user.email,
                        template_key="sso_migration",
                        subject=f"{tenant.name} has moved to Microsoft sign-in",
                        correlation_id=activation_id,
                        template_data={
                            "recipient_name": user.display_name,
                            "tenant_name": tenant.name,
                            "effective_time": now.strftime("%d %B %Y at %H:%M UTC"),
                            "action_url": tenant_frontend_url(settings, tenant.slug, "/sign-in"),
                            "action_label": "Sign in with Microsoft",
                        },
                    ),
                    settings,
                )
    result = await get_sso_configuration(tenant.tenant_id, settings, session)
    return SSOActivationResult(**result.model_dump())


async def issue_recovery(
    command: SSORecoveryCommand,
    platform_identity: SessionIdentity,
    tenant: ResolvedTenant,
    settings: Settings,
    session: AsyncSession,
) -> SSORecoveryResult:
    now = datetime.now(UTC)
    raw_token = f"{tenant.tenant_id}.{generate_session_token()}"
    expires_at = now + timedelta(minutes=settings.sso_recovery_minutes)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        row = (
            await session.execute(
                select(Membership, User)
                .join(User, User.id == Membership.user_id)
                .join(membership_roles, membership_roles.c.membership_id == Membership.id)
                .join(Role, Role.id == membership_roles.c.role_id)
                .where(
                    Membership.id == command.membership_id,
                    Membership.tenant_id == tenant.tenant_id,
                    Membership.status == MembershipStatus.ACTIVE,
                    Role.key == "tenant_admin",
                )
            )
        ).one_or_none()
        if row is None:
            raise SSOConfigurationError("Select an active tenant administrator for recovery.")
        _, user = row
        session.add(
            SSORecoveryToken(
                tenant_id=tenant.tenant_id,
                user_id=user.id,
                issued_by_user_id=platform_identity.user.id,
                incident_reference=command.incident_reference,
                token_hash=hash_session_token(raw_token),
                expires_at=expires_at,
            )
        )
        enqueue_email(
            session,
            EmailMessage(
                tenant_id=tenant.tenant_id,
                recipient=user.email,
                template_key="sso_recovery",
                subject=f"Restricted SSO recovery for {tenant.name}",
                template_data={
                    "recipient_name": user.display_name,
                    "tenant_name": tenant.name,
                    "incident_reference": command.incident_reference,
                    "expires_in": f"{settings.sso_recovery_minutes} minutes",
                    "action_url": tenant_frontend_url(
                        settings, tenant.slug, f"/admin/sso-recovery?token={raw_token}"
                    ),
                    "action_label": "Open restricted recovery",
                },
            ),
            settings,
            sensitive_template_data={
                "action_url": tenant_frontend_url(
                    settings, tenant.slug, f"/admin/sso-recovery?token={raw_token}"
                )
            },
        )
    return SSORecoveryResult(expires_at=expires_at)


async def redeem_recovery(
    token: str,
    tenant: ResolvedTenant,
    client: ClientContext,
    settings: Settings,
    session: AsyncSession,
) -> IssuedSession:
    now = datetime.now(UTC)
    tenant_prefix, separator, _ = token.partition(".")
    if not separator or tenant_prefix != str(tenant.tenant_id):
        raise SSOAuthenticationError("This recovery link is invalid or expired.")
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant.tenant_id)
        recovery = await session.scalar(
            select(SSORecoveryToken)
            .where(
                SSORecoveryToken.tenant_id == tenant.tenant_id,
                SSORecoveryToken.token_hash == hash_session_token(token),
                SSORecoveryToken.consumed_at.is_(None),
                SSORecoveryToken.revoked_at.is_(None),
                SSORecoveryToken.expires_at > now,
            )
            .with_for_update()
        )
        if recovery is None:
            raise SSOAuthenticationError("This recovery link is invalid or expired.")
        user = await session.get(User, recovery.user_id)
        membership = await session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant.tenant_id,
                Membership.user_id == recovery.user_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        if user is None or membership is None:
            raise SSOAuthenticationError("The recovery administrator is no longer active.")
        recovery.consumed_at = now
        raw_session = generate_session_token()
        csrf = generate_session_token()
        expires_at = min(recovery.expires_at, now + timedelta(minutes=30))
        session.add(
            AuthSession(
                tenant_id=tenant.tenant_id,
                user_id=user.id,
                token_hash=hash_session_token(raw_session),
                expires_at=expires_at,
                scope="sso_recovery",
                incident_reference=recovery.incident_reference,
            )
        )
        roles = list(
            await session.scalars(
                select(Role.key)
                .join(membership_roles, membership_roles.c.role_id == Role.id)
                .where(membership_roles.c.membership_id == membership.id)
            )
        )
        identity = SessionIdentity(
            user=AuthenticatedUser(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                is_platform_admin=user.is_platform_admin,
            ),
            tenant=AuthenticatedTenant(id=tenant.tenant_id, slug=tenant.slug, name=tenant.name),
            roles=roles,
            expires_at=expires_at,
            session_scope="sso_recovery",
        )
        return IssuedSession(
            token=raw_session,
            csrf_token=csrf,
            identity=identity,
            persistent=False,
        )


async def repair_sso_configuration(
    directory_id: uuid.UUID,
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        config = await _configuration(session, tenant_id, for_update=True)
        if config is None:
            raise SSOConfigurationError("The tenant has no SSO configuration to repair.")
        config.entra_directory_id = str(directory_id)
        config.status = "configured"
        config.validated_at = None
        config.validated_by_user_id = None
