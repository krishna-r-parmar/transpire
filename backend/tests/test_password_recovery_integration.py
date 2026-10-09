import os
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import session_factory
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.communications.models import EmailDelivery, EmailDeliveryStatus
from app.domains.communications.outbox import process_email_batch
from app.domains.communications.security import decrypt_template_data
from app.domains.identity.models import User
from app.domains.identity.repositories import SQLAlchemyIdentityRepository
from app.domains.identity.services import hash_password
from app.domains.tenants.models import Tenant
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


@pytest.mark.asyncio
async def test_password_recovery_is_generic_single_use_and_revokes_sessions() -> None:
    # Integration tests must never deliver through a developer's configured SMTP account.
    settings = get_settings().model_copy(update={"email_backend": "console"})
    original_password = settings.development_admin_password.get_secret_value()
    replacement_password = "A-new-local-password#2026"
    transport = httpx.ASGITransport(app=app)
    tenant_prefix = f"/api/v1/t/{settings.development_tenant_slug}"

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        signed_in = await client.post(
            f"{tenant_prefix}/auth/sign-in",
            json={
                "email": str(settings.development_admin_email),
                "password": original_password,
                "remember_me": False,
            },
        )
        assert signed_in.status_code == 200

        unknown = await client.post(
            f"{tenant_prefix}/auth/password-reset/request",
            json={"email": "unknown@example.com"},
        )
        known = await client.post(
            f"{tenant_prefix}/auth/password-reset/request",
            json={"email": str(settings.development_admin_email)},
        )
        assert unknown.status_code == known.status_code == 202
        assert unknown.json() == known.json()

        async with session_factory() as session:
            delivery = await session.scalar(
                select(EmailDelivery)
                .where(EmailDelivery.template_key == "password_reset")
                .order_by(EmailDelivery.created_at.desc())
                .limit(1)
            )
        assert delivery is not None
        assert "action_url" not in delivery.template_data
        assert delivery.encrypted_template_data is not None
        sensitive_data = decrypt_template_data(
            delivery.encrypted_template_data,
            settings,
        )
        reset_url = urlparse(str(sensitive_data["action_url"]))
        assert reset_url.path == f"/t/{settings.development_tenant_slug}/reset-password"
        token = parse_qs(reset_url.query)["token"][0]

        completed = await client.post(
            f"{tenant_prefix}/auth/password-reset/complete",
            json={"token": token, "new_password": replacement_password},
        )
        reused = await client.post(
            f"{tenant_prefix}/auth/password-reset/complete",
            json={"token": token, "new_password": replacement_password},
        )
        revoked_session = await client.get(f"{tenant_prefix}/auth/session")
        old_login = await client.post(
            f"{tenant_prefix}/auth/sign-in",
            json={
                "email": str(settings.development_admin_email),
                "password": original_password,
            },
        )
        new_login = await client.post(
            f"{tenant_prefix}/auth/sign-in",
            json={
                "email": str(settings.development_admin_email),
                "password": replacement_password,
            },
        )

        assert completed.status_code == 200
        assert reused.status_code == 400
        assert revoked_session.status_code == 401
        assert old_login.status_code == 401
        assert new_login.status_code == 200

    processed = await process_email_batch(limit=1000, settings=settings)
    assert processed >= 2

    async with session_factory() as session:
        refreshed = await session.get(EmailDelivery, delivery.id)
    assert refreshed is not None
    assert refreshed.status == EmailDeliveryStatus.SENT

    repository = SQLAlchemyIdentityRepository()
    async with session_factory() as session, session.begin():
        tenant = await session.scalar(
            select(Tenant).where(Tenant.slug == settings.development_tenant_slug)
        )
        assert tenant is not None
        await apply_tenant_to_transaction(session, tenant.id)
        user = await session.scalar(
            select(User).where(User.email == str(settings.development_admin_email))
        )
        assert user is not None
        user.password_hash = hash_password(original_password)
        await repository.revoke_user_sessions(
            session,
            tenant.id,
            user.id,
            datetime.now(UTC),
        )
