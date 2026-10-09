import os
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import session_factory
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.communications.models import EmailDelivery
from app.domains.communications.security import decrypt_template_data
from app.domains.identity.models import (
    AuthSession,
    Membership,
    MembershipStatus,
    SSORecoveryToken,
    TenantSSOConfiguration,
    User,
)
from app.domains.tenants.models import Tenant
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


@pytest.mark.asyncio
async def test_sso_cutover_preserves_identities_notifies_once_and_restricts_recovery() -> None:
    settings = get_settings()
    tenant_prefix = f"/api/v1/t/{settings.development_tenant_slug}"
    directory_id = str(uuid.uuid4())
    repaired_directory_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app)

    async with session_factory() as session, session.begin():
        tenant = await session.scalar(
            select(Tenant).where(Tenant.slug == settings.development_tenant_slug)
        )
        assert tenant is not None
        await apply_tenant_to_transaction(session, tenant.id)
        await session.execute(
            delete(EmailDelivery).where(
                EmailDelivery.tenant_id == tenant.id,
                EmailDelivery.template_key.in_(("sso_migration", "sso_recovery")),
            )
        )
        await session.execute(
            delete(SSORecoveryToken).where(SSORecoveryToken.tenant_id == tenant.id)
        )
        await session.execute(
            delete(TenantSSOConfiguration).where(
                TenantSSOConfiguration.tenant_id == tenant.id
            )
        )
        user = await session.scalar(
            select(User).where(User.email == str(settings.development_admin_email))
        )
        assert user is not None
        active_memberships = list(
            await session.scalars(
                select(Membership).where(
                    Membership.tenant_id == tenant.id,
                    Membership.status == MembershipStatus.ACTIVE,
                )
            )
        )
        identity_snapshot = {(membership.id, membership.user_id) for membership in active_memberships}
        session.add(
            TenantSSOConfiguration(
                tenant_id=tenant.id,
                entra_directory_id=directory_id,
                status="validated",
                validated_at=datetime.now(UTC),
                validated_by_user_id=user.id,
            )
        )
        tenant_id = tenant.id
        user_id = user.id
        admin_membership_id = next(
            membership.id for membership in active_memberships if membership.user_id == user.id
        )

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            signed_in = await client.post(
                f"{tenant_prefix}/auth/sign-in",
                json={
                    "email": str(settings.development_admin_email),
                    "password": settings.development_admin_password.get_secret_value(),
                },
            )
            assert signed_in.status_code == 200
            csrf = client.cookies.get(settings.csrf_cookie_name)
            assert csrf

            activated = await client.post(
                f"{tenant_prefix}/admin/sso/activate",
                headers={"X-CSRF-Token": csrf},
            )
            repeated = await client.post(
                f"{tenant_prefix}/admin/sso/activate",
                headers={"X-CSRF-Token": csrf},
            )
            existing_session = await client.get(f"{tenant_prefix}/auth/session")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as password_client:
                password_sign_in = await password_client.post(
                    f"{tenant_prefix}/auth/sign-in",
                    json={
                        "email": str(settings.development_admin_email),
                        "password": settings.development_admin_password.get_secret_value(),
                    },
                )

            assert activated.status_code == repeated.status_code == 200
            assert existing_session.status_code == 200
            assert password_sign_in.status_code == 409

            recovery = await client.post(
                f"{tenant_prefix}/platform/tenants/{tenant_id}/sso/recovery",
                headers={"X-CSRF-Token": csrf},
                json={
                    "membership_id": str(admin_membership_id),
                    "incident_reference": "INC-SSO-2041",
                },
            )
            assert recovery.status_code == 202, recovery.text

        async with session_factory() as session, session.begin():
            await apply_tenant_to_transaction(session, tenant_id)
            notifications = list(
                await session.scalars(
                    select(EmailDelivery).where(
                        EmailDelivery.tenant_id == tenant_id,
                        EmailDelivery.template_key == "sso_migration",
                    )
                )
            )
            assert len(notifications) == len(identity_snapshot)
            recovery_delivery = await session.scalar(
                select(EmailDelivery)
                .where(
                    EmailDelivery.tenant_id == tenant_id,
                    EmailDelivery.template_key == "sso_recovery",
                )
                .order_by(EmailDelivery.created_at.desc())
                .limit(1)
            )
            assert recovery_delivery is not None
            secure_data = decrypt_template_data(
                recovery_delivery.encrypted_template_data or "", settings
            )
            token = parse_qs(urlparse(str(secure_data["action_url"])).query)["token"][0]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as recovery_client:
            redeemed = await recovery_client.post(
                f"{tenant_prefix}/auth/sso/recovery/redeem", json={"token": token}
            )
            assert redeemed.status_code == 204
            recovery_csrf = recovery_client.cookies.get(settings.csrf_cookie_name)
            assert recovery_csrf
            blocked_from_people = await recovery_client.get(
                f"{tenant_prefix}/admin/members"
            )
            repaired = await recovery_client.put(
                f"{tenant_prefix}/admin/sso/recovery",
                headers={"X-CSRF-Token": recovery_csrf},
                json={"entra_directory_id": repaired_directory_id},
            )
            assert blocked_from_people.status_code == 403
            assert repaired.status_code == 204

        async with session_factory() as session, session.begin():
            await apply_tenant_to_transaction(session, tenant_id)
            memberships_after = list(
                await session.scalars(
                    select(Membership).where(
                        Membership.tenant_id == tenant_id,
                        Membership.status == MembershipStatus.ACTIVE,
                    )
                )
            )
            assert {(membership.id, membership.user_id) for membership in memberships_after} == identity_snapshot
            assert await session.get(User, user_id) is not None
            config = await session.scalar(
                select(TenantSSOConfiguration).where(
                    TenantSSOConfiguration.tenant_id == tenant_id
                )
            )
            assert config is not None
            assert config.entra_directory_id == repaired_directory_id
            assert config.status == "configured"
    finally:
        async with session_factory() as session, session.begin():
            await apply_tenant_to_transaction(session, tenant_id)
            await session.execute(
                delete(EmailDelivery).where(
                    EmailDelivery.tenant_id == tenant_id,
                    EmailDelivery.template_key.in_(("sso_migration", "sso_recovery")),
                )
            )
            await session.execute(
                delete(SSORecoveryToken).where(SSORecoveryToken.tenant_id == tenant_id)
            )
            await session.execute(
                delete(AuthSession).where(
                    AuthSession.tenant_id == tenant_id,
                    AuthSession.scope == "sso_recovery",
                )
            )
            await session.execute(
                delete(TenantSSOConfiguration).where(
                    TenantSSOConfiguration.tenant_id == tenant_id
                )
            )
