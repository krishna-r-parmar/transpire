import os
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import session_factory
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.communications.models import EmailDelivery
from app.domains.communications.security import decrypt_template_data
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

PASSWORD = "Secure-review-notify#2026"
HEADER = (
    "Username,First Name,Middle Name,Last Name,Location  Name,Department Name,"
    "Sub-Department Name,Business  Email Information Email Address,Manager User Sys ID,"
    "Manager,HOD  Job Relationships User ID,HOD  Job Relationships Name"
)


async def _join(client: httpx.AsyncClient, tenant_id: uuid.UUID, prefix: str, email: str) -> dict:
    async with session_factory() as session, session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        delivery = await session.scalar(
            select(EmailDelivery)
            .where(EmailDelivery.tenant_id == tenant_id, EmailDelivery.recipient == email)
            .where(EmailDelivery.template_key == "invitation")
            .order_by(EmailDelivery.created_at.desc())
            .limit(1)
        )
    assert delivery is not None and delivery.encrypted_template_data is not None
    data = decrypt_template_data(delivery.encrypted_template_data, get_settings())
    token = parse_qs(urlparse(str(data["action_url"])).query)["token"][0]
    accepted = await client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "new_password": PASSWORD}
    )
    assert accepted.status_code == 200, accepted.text
    return await _relogin(client, prefix, email)


def hr_rows(suffix: str, rows: list[tuple[str, str, str, str | None, str | None]]) -> bytes:
    lines = [HEADER]
    for employee_id, name, location, manager, hod in rows:
        first, last = name.split(" ")
        lines.append(
            f"{employee_id},{first},,{last},{location},Ops,Unit,"
            f"{first.lower()}-{suffix}@example.com,{manager or ''},,{hod or ''},"
        )
    return "\n".join(lines).encode()


async def _mail(tenant_id: uuid.UUID, recipient: str) -> list[str]:
    async with session_factory() as session, session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        return list(
            (
                await session.scalars(
                    select(EmailDelivery.template_key)
                    .where(
                        EmailDelivery.tenant_id == tenant_id, EmailDelivery.recipient == recipient
                    )
                    .order_by(EmailDelivery.created_at)
                )
            ).all()
        )


@pytest.mark.asyncio
async def test_hods_are_consulted_comments_gate_decisions_and_roles_are_announced() -> None:
    settings = get_settings()
    suffix = uuid.uuid4().hex[:8]
    slug = f"review-{suffix}"
    prefix = f"/api/v1/t/{slug}"
    owner_email = f"owner-{suffix}@example.com"
    transport = httpx.ASGITransport(app=app)

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")

    # Umang's HoD is Hema. Harsh is another HoD at the same site (he heads Isha);
    # Kavya heads a team at a different site and must not be consulted.
    staff = [
        ("100", "Umang Shah", "Bavla", "200", "200"),
        ("200", "Hema Rao", "Bavla", None, None),
        ("300", "Harsh Iyer", "Bavla", None, None),
        ("301", "Isha Nair", "Bavla", "300", "300"),
        ("400", "Kavya Das", "Ankleshwar", None, None),
        ("401", "Kiran Bose", "Ankleshwar", "400", "400"),
    ]
    email = {
        name.split(" ")[0]: f"{name.split(' ')[0].lower()}-{suffix}@example.com"
        for _, name, *_ in staff
    }

    async with client() as platform:
        platform_prefix = f"/api/v1/t/{settings.development_tenant_slug}"
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
                "slug": slug,
                "name": f"Review {suffix}",
                "first_admin_email": owner_email,
                "first_admin_name": "Review Owner",
            },
            headers={"X-CSRF-Token": platform.cookies.get(settings.csrf_cookie_name) or ""},
        )
        assert provisioned.status_code == 201, provisioned.text
        tenant_id = uuid.UUID(provisioned.json()["id"])

    async with (
        client() as owner,
        client() as umang,
        client() as hema,
        client() as harsh,
        client() as kavya,
    ):
        owner_h = await _join(owner, tenant_id, prefix, owner_email)
        await owner.put(
            f"{prefix}/admin/directory/settings",
            json={"invite_new_employees": True},
            headers=owner_h,
        )
        applied = await owner.post(
            f"{prefix}/admin/directory/upload",
            params={"file_name": "hr.csv", "mode": "apply"},
            content=hr_rows(suffix, staff),
            headers=owner_h,
        )
        assert applied.json()["status"] == "applied", applied.text
        umang_h = await _join(umang, tenant_id, prefix, email["Umang"])
        hema_h = await _join(hema, tenant_id, prefix, email["Hema"])
        harsh_h = await _join(harsh, tenant_id, prefix, email["Harsh"])
        await _join(kavya, tenant_id, prefix, email["Kavya"])
        relink = await owner.post(
            f"{prefix}/admin/directory/upload",
            params={"file_name": "hr2.csv", "mode": "apply"},
            content=hr_rows(suffix, [(*row[:2], f"{row[2]} ", *row[3:]) for row in staff]),
            headers=owner_h,
        )
        assert relink.json()["status"] == "applied"

        # User groups carry a purpose; notification-only groups can never approve.
        members = {m["email"]: m["id"] for m in (await owner.get(f"{prefix}/admin/members")).json()}
        notify_only = await owner.post(
            f"{prefix}/admin/configuration/approver-groups",
            json={
                "name": "Plant leads",
                "purpose": "notification",
                "member_membership_ids": [members[email["Kavya"]]],
            },
            headers=owner_h,
        )
        assert notify_only.json()["purpose"] == "notification"
        workflow = (await owner.get(f"{prefix}/admin/configuration/workflows/contracts")).json()[0]
        wrong = await owner.post(
            f"{prefix}/admin/configuration/workflows/{workflow['id']}/versions",
            json={
                "stages": [
                    {
                        "key": "leads",
                        "name": "Leads",
                        "source": "group",
                        "group_id": notify_only.json()["id"],
                    }
                ]
            },
            headers=owner_h,
        )
        assert wrong.status_code == 409

        draft = await owner.post(
            f"{prefix}/admin/configuration/workflows/{workflow['id']}/versions",
            json={
                "stages": [
                    {
                        "key": "hod",
                        "name": "Head of department",
                        "source": "dynamic",
                        "relationship": "hod",
                        "notify_kind": "hods_same_location",
                    }
                ]
            },
            headers=owner_h,
        )
        assert draft.status_code == 201, draft.text
        assert (
            await owner.post(
                f"{prefix}/admin/configuration/workflows/{workflow['id']}/versions/{draft.json()['id']}/publish",
                headers=owner_h,
            )
        ).status_code == 204

        category = await owner.post(
            f"{prefix}/admin/configuration/master-data/category",
            json={"code": "safety", "name": "Safety"},
            headers=owner_h,
        )
        sub = await owner.post(
            f"{prefix}/admin/configuration/master-data/subcategory",
            json={"code": "ergo", "name": "Ergonomics", "parent_id": category.json()["id"]},
            headers=owner_h,
        )
        area = await owner.post(
            f"{prefix}/admin/configuration/master-data/process_area",
            json={"code": "pack", "name": "Packaging"},
            headers=owner_h,
        )
        command = {
            "idea_type": "kaizen",
            "category_id": category.json()["id"],
            "subcategory_id": sub.json()["id"],
            "process_area_id": area.json()["id"],
            "title": "Shared torque tools",
            "problem_statement": "Each line buys its own torque tools.",
            "business_case": "Sharing cuts spend.",
            "current_state": "6 sets",
            "target_state": "3 sets",
            "impacts": ["cost"],
            "estimated_annual_saving": "50000",
        }
        idea = await umang.post(f"{prefix}/ideas", json=command, headers=umang_h)
        idea_id = idea.json()["id"]
        submitted = await umang.post(
            f"{prefix}/ideas/{idea_id}/submit", json=command, headers=umang_h
        )
        assert submitted.status_code == 200, submitted.text

        # Hema is asked to decide; Harsh (same site HoD) is asked for comments; Kavya is not.
        assert "approval_request" in await _mail(tenant_id, email["Hema"])
        assert "comment_request" in await _mail(tenant_id, email["Harsh"])
        assert "comment_request" not in await _mail(tenant_id, email["Kavya"])
        assert (await kavya.get(f"{prefix}/ideas/{idea_id}/comments")).status_code == 403

        harsh_thread = (await harsh.get(f"{prefix}/ideas/{idea_id}/comments")).json()
        assert harsh_thread["can_comment"] is True
        assert harsh_thread["consulted_on"] == ["Head of department"]
        posted = await harsh.post(
            f"{prefix}/ideas/{idea_id}/comments",
            json={"body": "Line 3 already shares tools; check calibration logs."},
            headers=harsh_h,
        )
        assert posted.status_code == 201, posted.text
        assert "comment_posted" in await _mail(tenant_id, email["Hema"])

        detail = (await hema.get(f"{prefix}/ideas/{idea_id}")).json()
        task = next(s for s in detail["approval_stages"] if s["is_actionable"])
        decide = f"{prefix}/ideas/{idea_id}/approvals/{task['id']}"
        blocked = await hema.post(
            decide, json={"decision": "approve", "comment": ""}, headers=hema_h
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "comments_need_review"
        assert (await hema.get(f"{prefix}/ideas/{idea_id}/comments")).json()[
            "unanswered_for_me"
        ] == 1

        comment_id = posted.json()["comments"][0]["id"]
        replied = await hema.post(
            f"{prefix}/ideas/{idea_id}/comments",
            json={"body": "Good point, will add calibration to the plan.", "parent_id": comment_id},
            headers=hema_h,
        )
        assert replied.status_code == 201
        assert "comment_posted" in await _mail(tenant_id, email["Harsh"])
        approved = await hema.post(
            decide, json={"decision": "approve", "comment": ""}, headers=hema_h
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert "project_charter_ready" in await _mail(tenant_id, email["Umang"])

        # Role changes always notify the person; elevated access also notifies other Owners.
        await owner.patch(
            f"{prefix}/admin/members/{members[email['Hema']]}/role",
            json={"role_key": "workspace_owner"},
            headers=owner_h,
        )
        assert "role_changed" in await _mail(tenant_id, email["Hema"])
        await hema.patch(
            f"{prefix}/admin/members/{members[email['Harsh']]}/role",
            json={"role_key": "tenant_admin"},
            headers=await _relogin(hema, prefix, email["Hema"]),
        )
        assert "role_changed" in await _mail(tenant_id, email["Harsh"])
        assert "privileged_role_granted" in await _mail(tenant_id, owner_email)
        assert "privileged_role_granted" not in await _mail(tenant_id, email["Hema"])  # the actor


async def _relogin(client: httpx.AsyncClient, prefix: str, email_address: str) -> dict:
    await client.post(f"{prefix}/auth/sign-in", json={"email": email_address, "password": PASSWORD})
    return {"X-CSRF-Token": client.cookies.get(get_settings().csrf_cookie_name) or ""}
