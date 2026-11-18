import os
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import session_factory
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.audit.models import AuditEvent
from app.domains.communications.models import EmailDelivery
from app.domains.communications.security import decrypt_template_data
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

PASSWORD = "Secure-reminder-password#2026"


async def _latest_invitation_token(tenant_id: uuid.UUID, email: str) -> str:
    settings = get_settings()
    async with session_factory() as session, session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        delivery = await session.scalar(
            select(EmailDelivery)
            .where(
                EmailDelivery.tenant_id == tenant_id,
                EmailDelivery.template_key == "invitation",
                EmailDelivery.recipient == email,
            )
            .order_by(EmailDelivery.created_at.desc())
            .limit(1)
        )
    assert delivery is not None and delivery.encrypted_template_data is not None
    secure_data = decrypt_template_data(delivery.encrypted_template_data, settings)
    return parse_qs(urlparse(str(secure_data["action_url"])).query)["token"][0]


async def _accept(client: httpx.AsyncClient, tenant_id: uuid.UUID, email: str) -> None:
    token = await _latest_invitation_token(tenant_id, email)
    accepted = await client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "new_password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text


async def _sign_in(client: httpx.AsyncClient, prefix: str, email: str, password: str) -> str:
    signed_in = await client.post(
        f"{prefix}/auth/sign-in", json={"email": email, "password": password}
    )
    assert signed_in.status_code == 200, signed_in.text
    csrf = client.cookies.get(get_settings().csrf_cookie_name)
    assert csrf
    return csrf


@pytest.mark.asyncio
async def test_admin_check_in_reminders_permissions_eligibility_and_cooldown() -> None:
    settings = get_settings()
    suffix = uuid.uuid4().hex[:8]
    tenant_slug = f"reminders-{suffix}"
    tenant_prefix = f"/api/v1/t/{tenant_slug}"
    platform_prefix = f"/api/v1/t/{settings.development_tenant_slug}"
    admin_email = f"admin-{suffix}@example.com"
    member_email = f"member-{suffix}@example.com"
    transport = httpx.ASGITransport(app=app)

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")

    async with client() as platform:
        platform_csrf = await _sign_in(
            platform,
            platform_prefix,
            str(settings.development_admin_email),
            settings.development_admin_password.get_secret_value(),
        )
        provisioned = await platform.post(
            f"{platform_prefix}/platform/tenants",
            json={
                "slug": tenant_slug,
                "name": f"Reminders {suffix}",
                "first_admin_email": admin_email,
                "first_admin_name": "Reminder Administrator",
            },
            headers={"X-CSRF-Token": platform_csrf},
        )
        assert provisioned.status_code == 201, provisioned.text
        tenant_id = uuid.UUID(provisioned.json()["id"])

    async with client() as admin, client() as member:
        await _accept(admin, tenant_id, admin_email)
        admin_csrf = await _sign_in(admin, tenant_prefix, admin_email, PASSWORD)

        invited = await admin.post(
            f"{tenant_prefix}/admin/invitations",
            json={
                "email": member_email,
                "display_name": "Never Signed-In",
                "role_key": "idea_submitter",
            },
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert invited.status_code == 202, invited.text
        await _accept(member, tenant_id, member_email)

        # Eligibility: everyone active is listed; inactive_days narrows to people
        # who never signed in or have not signed in within that window.
        overview = await admin.get(f"{tenant_prefix}/admin/check-in-reminders")
        assert overview.status_code == 200, overview.text
        assert overview.json()["cooldown_hours"] == settings.check_in_reminder_cooldown_hours
        by_email = {row["email"]: row for row in overview.json()["candidates"]}
        assert set(by_email) == {admin_email, member_email}
        assert by_email[admin_email]["last_signed_in_at"] is not None
        assert by_email[member_email]["last_signed_in_at"] is None
        assert by_email[member_email]["last_reminded_at"] is None
        assert by_email[member_email]["cooldown_until"] is None
        member_id = by_email[member_email]["membership_id"]

        # The People directory carries the same last sign-in for every member.
        directory = await admin.get(f"{tenant_prefix}/admin/members")
        assert directory.status_code == 200, directory.text
        directory_by_email = {row["email"]: row for row in directory.json()}
        assert directory_by_email[admin_email]["last_signed_in_at"] is not None
        assert directory_by_email[member_email]["last_signed_in_at"] is None

        inactive = await admin.get(
            f"{tenant_prefix}/admin/check-in-reminders", params={"inactive_days": 30}
        )
        assert inactive.status_code == 200, inactive.text
        assert [row["email"] for row in inactive.json()["candidates"]] == [member_email]

        invalid_window = await admin.get(
            f"{tenant_prefix}/admin/check-in-reminders", params={"inactive_days": 0}
        )
        assert invalid_window.status_code == 422

        # Preview renders the real template.
        preview = await admin.get(f"{tenant_prefix}/admin/check-in-reminders/preview")
        assert preview.status_code == 200, preview.text
        assert "Manage preferences" in preview.json()["html_body"]
        assert f"/t/{tenant_slug}/sign-in" in preview.json()["text_body"]

        # Non-administrators cannot list, preview or send.
        member_csrf = await _sign_in(member, tenant_prefix, member_email, PASSWORD)
        assert (await member.get(f"{tenant_prefix}/admin/check-in-reminders")).status_code == 403
        assert (
            await member.get(f"{tenant_prefix}/admin/check-in-reminders/preview")
        ).status_code == 403
        assert (
            await member.post(
                f"{tenant_prefix}/admin/check-in-reminders",
                json={"membership_ids": [member_id]},
                headers={"X-CSRF-Token": member_csrf},
            )
        ).status_code == 403

        # Unauthenticated callers are rejected too.
        async with client() as anonymous:
            assert (
                await anonymous.get(f"{tenant_prefix}/admin/check-in-reminders")
            ).status_code == 401

        # State-changing requests still need the CSRF token.
        without_csrf = await admin.post(
            f"{tenant_prefix}/admin/check-in-reminders",
            json={"membership_ids": [member_id]},
        )
        assert without_csrf.status_code == 403

        unknown_id = str(uuid.uuid4())
        sent = await admin.post(
            f"{tenant_prefix}/admin/check-in-reminders",
            json={"membership_ids": [member_id, member_id, unknown_id]},
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert sent.status_code == 202, sent.text
        assert sent.json()["queued"] == [member_id]
        assert sent.json()["skipped"] == [{"membership_id": unknown_id, "reason": "not_eligible"}]

        # Cooldown: a second send inside the window is skipped, not queued.
        repeated = await admin.post(
            f"{tenant_prefix}/admin/check-in-reminders",
            json={"membership_ids": [member_id]},
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert repeated.status_code == 202, repeated.text
        assert repeated.json()["queued"] == []
        assert repeated.json()["skipped"] == [{"membership_id": member_id, "reason": "cooldown"}]

        after = await admin.get(f"{tenant_prefix}/admin/check-in-reminders")
        reminded = next(row for row in after.json()["candidates"] if row["membership_id"] == member_id)
        assert reminded["last_reminded_at"] is not None
        assert reminded["reminder_count"] == 1
        assert reminded["cooldown_until"] is not None
        assert reminded["last_signed_in_at"] is not None

    async with session_factory() as session, session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        deliveries = (
            await session.scalars(
                select(EmailDelivery).where(
                    EmailDelivery.tenant_id == tenant_id,
                    EmailDelivery.template_key == "check_in_reminder",
                )
            )
        ).all()
        audit_events = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.event_type == "check_in_reminder.sent",
                )
            )
        ).all()
    assert [delivery.recipient for delivery in deliveries] == [member_email]
    assert "note" not in deliveries[0].template_data
    assert "sender_name" not in deliveries[0].template_data
    assert str(deliveries[0].template_data["secondary_url"]).endswith(f"/t/{tenant_slug}/profile")
    assert str(deliveries[0].template_data["action_url"]).endswith(f"/t/{tenant_slug}/sign-in")
    assert len(audit_events) == 1
