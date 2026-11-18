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

PASSWORD = "Secure-role-ladder-password#2026"


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


async def _join(
    client: httpx.AsyncClient, tenant_id: uuid.UUID, prefix: str, email: str
) -> dict[str, str]:
    token = await _latest_invitation_token(tenant_id, email)
    accepted = await client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "new_password": PASSWORD}
    )
    assert accepted.status_code == 200, accepted.text
    signed_in = await client.post(
        f"{prefix}/auth/sign-in", json={"email": email, "password": PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    csrf = client.cookies.get(get_settings().csrf_cookie_name)
    assert csrf
    return {"X-CSRF-Token": csrf}


@pytest.mark.asyncio
async def test_workspace_role_ladder() -> None:
    settings = get_settings()
    suffix = uuid.uuid4().hex[:8]
    prefix = f"/api/v1/t/roles-{suffix}"
    platform_prefix = f"/api/v1/t/{settings.development_tenant_slug}"
    emails = {
        role: f"{role}-{suffix}@example.com" for role in ("owner", "admin", "contributor", "viewer")
    }
    transport = httpx.ASGITransport(app=app)

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")

    async with client() as platform:
        await platform.post(
            f"{platform_prefix}/auth/sign-in",
            json={
                "email": str(settings.development_admin_email),
                "password": settings.development_admin_password.get_secret_value(),
            },
        )
        provisioned = await platform.post(
            f"{platform_prefix}/platform/tenants",
            json={
                "slug": f"roles-{suffix}",
                "name": f"Roles {suffix}",
                "first_admin_email": emails["owner"],
                "first_admin_name": "First Owner",
            },
            headers={"X-CSRF-Token": platform.cookies.get(settings.csrf_cookie_name) or ""},
        )
        assert provisioned.status_code == 201, provisioned.text
        tenant_id = uuid.UUID(provisioned.json()["id"])

    async with client() as owner, client() as admin, client() as contributor, client() as viewer:
        owner_h = await _join(owner, tenant_id, prefix, emails["owner"])

        # The first person in a new workspace is its Workspace Owner.
        session = (await owner.get(f"{prefix}/auth/session")).json()
        assert session["roles"] == ["workspace_owner"]

        for role, key in (
            ("admin", "tenant_admin"),
            ("contributor", "idea_submitter"),
            ("viewer", "viewer"),
        ):
            invited = await owner.post(
                f"{prefix}/admin/invitations",
                json={"email": emails[role], "display_name": role.title(), "role_key": key},
                headers=owner_h,
            )
            assert invited.status_code == 202, invited.text
        admin_h = await _join(admin, tenant_id, prefix, emails["admin"])
        contributor_h = await _join(contributor, tenant_id, prefix, emails["contributor"])
        viewer_h = await _join(viewer, tenant_id, prefix, emails["viewer"])

        members = {row["email"]: row for row in (await owner.get(f"{prefix}/admin/members")).json()}

        # Role catalogue reflects what the caller may grant.
        owner_roles = {r["key"]: r for r in (await owner.get(f"{prefix}/admin/roles")).json()}
        assert [r["name"] for r in sorted(owner_roles.values(), key=lambda r: r["rank"])] == [
            "Viewer",
            "Contributor",
            "Workspace Admin",
            "Workspace Owner",
        ]
        assert all(r["assignable"] for r in owner_roles.values())
        admin_roles = {
            r["key"]: r["assignable"] for r in (await admin.get(f"{prefix}/admin/roles")).json()
        }
        assert admin_roles == {
            "viewer": True,
            "idea_submitter": True,
            "tenant_admin": False,
            "workspace_owner": False,
        }

        # Admins cannot invite or touch Admins/Owners.
        for key in ("tenant_admin", "workspace_owner"):
            denied = await admin.post(
                f"{prefix}/admin/invitations",
                json={
                    "email": f"x-{key}-{suffix}@example.com",
                    "display_name": "Denied",
                    "role_key": key,
                },
                headers=admin_h,
            )
            assert denied.status_code == 403, denied.text
        owner_id = members[emails["owner"]]["id"]
        assert (
            await admin.patch(
                f"{prefix}/admin/members/{owner_id}/role",
                json={"role_key": "viewer"},
                headers=admin_h,
            )
        ).status_code == 403
        assert (
            await admin.patch(
                f"{prefix}/admin/members/{owner_id}/status",
                json={"status": "inactive"},
                headers=admin_h,
            )
        ).status_code == 403
        admin_view = {
            r["email"]: r["can_manage"] for r in (await admin.get(f"{prefix}/admin/members")).json()
        }
        assert admin_view[emails["owner"]] is False
        assert admin_view[emails["admin"]] is False  # never yourself
        assert admin_view[emails["contributor"]] is True

        # Nobody changes their own role.
        own_id = members[emails["owner"]]["id"]
        assert (
            await owner.patch(
                f"{prefix}/admin/members/{own_id}/role",
                json={"role_key": "tenant_admin"},
                headers=owner_h,
            )
        ).status_code == 409

        # Admin can move a Contributor to Viewer; the change is audited.
        contributor_id = members[emails["contributor"]]["id"]
        changed = await admin.patch(
            f"{prefix}/admin/members/{contributor_id}/role",
            json={"role_key": "viewer"},
            headers=admin_h,
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["roles"] == ["viewer"]
        async with session_factory() as db, db.begin():
            await apply_tenant_to_transaction(db, tenant_id)
            event = await db.scalar(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.event_type == "member.role_changed",
                    AuditEvent.entity_id == uuid.UUID(contributor_id),
                )
            )
        assert event is not None
        assert event.details == {"from": ["idea_submitter"], "to": "viewer"}
        # Roles are read live, so the demoted session loses write access at once.
        assert (
            await contributor.post(f"{prefix}/ideas", json={}, headers=contributor_h)
        ).status_code == 403
        restored = await admin.patch(
            f"{prefix}/admin/members/{contributor_id}/role",
            json={"role_key": "idea_submitter"},
            headers=admin_h,
        )
        assert restored.status_code == 200, restored.text

        # Viewers read like Contributors but cannot write or administer.
        assert (await viewer.get(f"{prefix}/ideas")).status_code == 200
        assert (await viewer.get(f"{prefix}/projects")).status_code == 200
        assert (await viewer.post(f"{prefix}/ideas", json={}, headers=viewer_h)).status_code == 403
        assert (await viewer.get(f"{prefix}/admin/members")).status_code == 403

        # Viewers are never offered as approvers or project team members.
        assignees = {
            a["email"]
            for a in (await owner.get(f"{prefix}/admin/configuration/workflows/assignees")).json()
        }
        assert emails["viewer"] not in assignees and emails["contributor"] in assignees
        candidates = {
            c["email"] for c in (await owner.get(f"{prefix}/projects/team-candidates")).json()
        }
        assert emails["viewer"] not in candidates and emails["contributor"] in candidates

        # Sign-in and security settings belong to Owners.
        assert (await admin.get(f"{prefix}/admin/sso")).status_code == 403
        assert (await owner.get(f"{prefix}/admin/sso")).status_code == 200

        # Owners can grant ownership; a second Owner can then step the first down.
        admin_id = members[emails["admin"]]["id"]
        promoted = await owner.patch(
            f"{prefix}/admin/members/{admin_id}/role",
            json={"role_key": "workspace_owner"},
            headers=owner_h,
        )
        assert promoted.status_code == 200, promoted.text
        stepped_down = await admin.patch(
            f"{prefix}/admin/members/{owner_id}/role",
            json={"role_key": "tenant_admin"},
            headers=admin_h,
        )
        assert stepped_down.status_code == 200, stepped_down.text
        assert (await owner.get(f"{prefix}/admin/sso")).status_code == 403
