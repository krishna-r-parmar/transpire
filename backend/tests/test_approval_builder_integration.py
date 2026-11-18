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

PASSWORD = "Secure-approval-builder#2026"
HEADER = (
    "Username,First Name,Middle Name,Last Name,Location  Name,Department Name,"
    "Sub-Department Name,Business  Email Information Email Address,Manager User Sys ID,"
    "Manager,HOD  Job Relationships User ID,HOD  Job Relationships Name"
)


def hr_file(
    suffix: str, rows: list[tuple[str, str, str | None, str | None]], location: str
) -> bytes:
    lines = [HEADER]
    for employee_id, name, manager, hod in rows:
        first, last = name.split(" ")
        lines.append(
            f"{employee_id},{first},,{last},{location},Scale-up,Unit - 06,"
            f"{first.lower()}-{suffix}@example.com,{manager or ''},,{hod or ''},"
        )
    return "\n".join(lines).encode()


async def _token(tenant_id: uuid.UUID, email: str) -> str:
    async with session_factory() as session, session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        delivery = await session.scalar(
            select(EmailDelivery)
            .where(EmailDelivery.tenant_id == tenant_id, EmailDelivery.recipient == email)
            .order_by(EmailDelivery.created_at.desc())
            .limit(1)
        )
    assert delivery is not None and delivery.encrypted_template_data is not None
    data = decrypt_template_data(delivery.encrypted_template_data, get_settings())
    return parse_qs(urlparse(str(data["action_url"])).query)["token"][0]


async def _join(client: httpx.AsyncClient, tenant_id: uuid.UUID, prefix: str, email: str) -> dict:
    accepted = await client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": await _token(tenant_id, email), "new_password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    signed_in = await client.post(
        f"{prefix}/auth/sign-in", json={"email": email, "password": PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    return {"X-CSRF-Token": client.cookies.get(get_settings().csrf_cookie_name) or ""}


@pytest.mark.asyncio
async def test_hr_directory_drives_dynamic_approvals() -> None:
    settings = get_settings()
    suffix = uuid.uuid4().hex[:8]
    slug = f"builder-{suffix}"
    prefix = f"/api/v1/t/{slug}"
    owner_email = f"owner-{suffix}@example.com"
    transport = httpx.ASGITransport(app=app)

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")

    # Umang reports to Ravindrakumar; both roll up to Ashutosh (HoD). Ravindrakumar's
    # manager is also his HoD, and Ashutosh is the top of the chain.
    staff = [
        ("350395", "Umang Prajapati", "303359", "302992"),
        ("303359", "Ravindrakumar Patel", "302992", "302992"),
        ("302992", "Ashutosh Patel", None, None),
        ("400001", "Oscar Excellence", None, None),
        ("400002", "Fiona Finance", None, None),
    ]
    email = {
        name.split(" ")[0]: f"{name.split(' ')[0].lower()}-{suffix}@example.com"
        for _, name, _, _ in staff
    }

    async with client() as platform:
        await platform.post(
            f"/api/v1/t/{settings.development_tenant_slug}/auth/sign-in",
            json={
                "email": str(settings.development_admin_email),
                "password": settings.development_admin_password.get_secret_value(),
            },
        )
        provisioned = await platform.post(
            f"/api/v1/t/{settings.development_tenant_slug}/platform/tenants",
            json={
                "slug": slug,
                "name": f"Builder {suffix}",
                "first_admin_email": owner_email,
                "first_admin_name": "Builder Owner",
            },
            headers={"X-CSRF-Token": platform.cookies.get(settings.csrf_cookie_name) or ""},
        )
        assert provisioned.status_code == 201, provisioned.text
        tenant_id = uuid.UUID(provisioned.json()["id"])

    async with (
        client() as owner,
        client() as umang,
        client() as ravi,
        client() as ashu,
        client() as oscar,
        client() as fiona,
    ):
        owner_h = await _join(owner, tenant_id, prefix, owner_email)
        settings_saved = await owner.put(
            f"{prefix}/admin/directory/settings",
            json={"invite_new_employees": True, "allowed_email_domains": ["example.com"]},
            headers=owner_h,
        )
        assert settings_saved.status_code == 200, settings_saved.text

        # Preview changes nothing; apply loads everyone and invites them.
        first = hr_file(suffix, staff, "Bavla")
        upload = f"{prefix}/admin/directory/upload"
        preview = await owner.post(
            upload,
            params={"file_name": "day1.csv", "mode": "preview"},
            content=first,
            headers=owner_h,
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["status"] == "previewed"
        assert preview.json()["summary"]["new"] == 5
        assert (await owner.get(f"{prefix}/admin/directory")).json()["employees_active"] == 0
        applied = await owner.post(
            upload,
            params={"file_name": "day1.csv", "mode": "apply"},
            content=first,
            headers=owner_h,
        )
        assert applied.json()["status"] == "applied", applied.text
        assert applied.json()["summary"]["invited"] == 5
        again = await owner.post(
            upload,
            params={"file_name": "day1.csv", "mode": "apply"},
            content=first,
            headers=owner_h,
        )
        assert again.json()["status"] == "duplicate"

        umang_h = await _join(umang, tenant_id, prefix, email["Umang"])
        ravi_h = await _join(ravi, tenant_id, prefix, email["Ravindrakumar"])
        ashu_h = await _join(ashu, tenant_id, prefix, email["Ashutosh"])
        oscar_h = await _join(oscar, tenant_id, prefix, email["Oscar"])
        fiona_h = await _join(fiona, tenant_id, prefix, email["Fiona"])

        # Accounts that joined after the sync link to their HR records on the next run.
        relink = hr_file(suffix, staff, "Bavla ")
        assert (
            await owner.post(
                upload,
                params={"file_name": "day1b.csv", "mode": "apply"},
                content=relink,
                headers=owner_h,
            )
        ).json()["status"] == "applied"

        members = {m["email"]: m["id"] for m in (await owner.get(f"{prefix}/admin/members")).json()}
        groups = f"{prefix}/admin/configuration/approver-groups"
        oe = await owner.post(
            groups,
            json={"name": "OE Head", "member_membership_ids": [members[email["Oscar"]]]},
            headers=owner_h,
        )
        finance = await owner.post(
            groups,
            json={
                "name": "Finance Head",
                "member_membership_ids": [members[email["Fiona"]], members[owner_email]],
            },
            headers=owner_h,
        )
        assert oe.status_code == 201 and finance.status_code == 201, finance.text
        viewer_in_group = await owner.post(
            groups,
            json={"name": "Nobody", "member_membership_ids": [str(uuid.uuid4())]},
            headers=owner_h,
        )
        assert viewer_in_group.status_code == 409

        stages = [
            {
                "key": "rm",
                "name": "Reporting manager",
                "source": "dynamic",
                "relationship": "reporting_manager",
            },
            {
                "key": "hod",
                "name": "Head of department",
                "source": "dynamic",
                "relationship": "hod",
            },
            {
                "key": "oe",
                "name": "OE Head",
                "source": "group",
                "group_id": oe.json()["id"],
                "mode": "any",
            },
            {
                "key": "finance",
                "name": "Finance Head",
                "source": "group",
                "group_id": finance.json()["id"],
                "mode": "all_parallel",
            },
        ]

        # The builder's "test with an employee" explains every step.
        preview_url = f"{prefix}/admin/configuration/workflows/preview"
        for_umang = (
            await owner.post(
                preview_url, json={"stages": stages, "employee_id": "350395"}, headers=owner_h
            )
        ).json()
        assert [s["outcome"] for s in for_umang["steps"]] == ["assigned"] * 4
        assert for_umang["steps"][0]["approvers"][0]["display_name"] == "Ravindrakumar Patel"
        assert len(for_umang["steps"][3]["approvers"]) == 2
        for_ravi = (
            await owner.post(
                preview_url, json={"stages": stages, "employee_id": "303359"}, headers=owner_h
            )
        ).json()
        assert for_ravi["steps"][1]["outcome"] == "skipped"
        assert "same approver" in for_ravi["steps"][1]["note"]
        for_ashu = (
            await owner.post(
                preview_url, json={"stages": stages, "employee_id": "302992"}, headers=owner_h
            )
        ).json()
        assert [s["outcome"] for s in for_ashu["steps"][:2]] == ["skipped", "skipped"]

        workflow = (await owner.get(f"{prefix}/admin/configuration/workflows/contracts")).json()[0]
        draft = await owner.post(
            f"{prefix}/admin/configuration/workflows/{workflow['id']}/versions",
            json={"stages": stages},
            headers=owner_h,
        )
        assert draft.status_code == 201, draft.text
        published = await owner.post(
            f"{prefix}/admin/configuration/workflows/{workflow['id']}/versions/{draft.json()['id']}/publish",
            headers=owner_h,
        )
        assert published.status_code == 204, published.text

        catalog = (await umang.get(f"{prefix}/ideas/submission-catalog")).json()
        assert (
            catalog["approval_contract"]["stages"][0]["assignee_name"] == "Your reporting manager"
        )

        category = await owner.post(
            f"{prefix}/admin/configuration/master-data/category",
            json={"code": "safety", "name": "Safety"},
            headers=owner_h,
        )
        subcategory = await owner.post(
            f"{prefix}/admin/configuration/master-data/subcategory",
            json={"code": "ergonomics", "name": "Ergonomics", "parent_id": category.json()["id"]},
            headers=owner_h,
        )
        process_area = await owner.post(
            f"{prefix}/admin/configuration/master-data/process_area",
            json={"code": "packaging", "name": "Packaging"},
            headers=owner_h,
        )
        command = {
            "idea_type": "kaizen",
            "category_id": category.json()["id"],
            "subcategory_id": subcategory.json()["id"],
            "process_area_id": process_area.json()["id"],
            "title": "Standardise unit six checks",
            "problem_statement": "Manual checks slow every batch in unit six.",
            "business_case": "Digital checks cut waiting time.",
            "current_state": "18 minutes",
            "target_state": "8 minutes",
            "impacts": ["delivery"],
            "estimated_annual_saving": "100000",
        }
        draft_idea = await umang.post(f"{prefix}/ideas", json=command, headers=umang_h)
        assert draft_idea.status_code == 201, draft_idea.text
        idea_id = draft_idea.json()["id"]
        submitted = await umang.post(
            f"{prefix}/ideas/{idea_id}/submit", json=command, headers=umang_h
        )
        assert submitted.status_code == 200, submitted.text

        async def act(who: httpx.AsyncClient, headers: dict) -> dict:
            detail = (await who.get(f"{prefix}/ideas/{idea_id}")).json()
            mine = next(stage for stage in detail["approval_stages"] if stage["is_actionable"])
            decided = await who.post(
                f"{prefix}/ideas/{idea_id}/approvals/{mine['id']}",
                json={"decision": "approve", "comment": ""},
                headers=headers,
            )
            assert decided.status_code == 200, decided.text
            return decided.json()

        await act(ravi, ravi_h)  # RM step
        pending = [
            s
            for s in (await owner.get(f"{prefix}/ideas/{idea_id}")).json()["approval_stages"]
            if s["status"] == "pending"
        ]
        assert [s["assignee_name"] for s in pending] == ["Ashutosh Patel"]

        # Next day HR moves Umang under a new HoD (Oscar): the pending HoD task follows.
        moved = [
            ("350395", "Umang Prajapati", "303359", "400001"),
            *staff[1:],
        ]
        day2 = await owner.post(
            upload,
            params={"file_name": "day2.csv", "mode": "apply"},
            content=hr_file(suffix, moved, "Bavla"),
            headers=owner_h,
        )
        assert day2.json()["status"] == "applied", day2.text
        assert day2.json()["summary"]["changed"] == 1
        assert day2.json()["summary"]["rerouted"] == 1
        stages_now = (await owner.get(f"{prefix}/ideas/{idea_id}")).json()["approval_stages"]
        assert any(
            s["status"] == "reassigned" and s["assignee_name"] == "Ashutosh Patel"
            for s in stages_now
        )
        assert (await ashu.get(f"{prefix}/ideas/home-summary")).json()["approval_items"] == []

        await act(oscar, oscar_h)  # HoD step, now Oscar. The OE step is Oscar again: skipped.
        stages_now = (await owner.get(f"{prefix}/ideas/{idea_id}")).json()["approval_stages"]
        oe_step = [s for s in stages_now if s["stage_key"] == "oe"]
        assert [s["status"] for s in oe_step] == ["skipped"]
        finance_tasks = [
            s for s in stages_now if s["stage_key"] == "finance" and s["status"] == "pending"
        ]
        assert len(finance_tasks) == 2  # parallel: both at once

        after_fiona = await act(fiona, fiona_h)
        assert after_fiona["status"] == "submitted"  # still waiting for the second approver
        after_owner = await act(owner, owner_h)
        assert after_owner["status"] == "approved"

        # Leavers lose access only after two consecutive absences.
        without_fiona = [row for row in moved if row[0] != "400002"]
        day3 = await owner.post(
            upload,
            params={"file_name": "day3.csv", "mode": "apply"},
            content=hr_file(suffix, without_fiona, "Bavla"),
            headers=owner_h,
        )
        assert day3.json()["summary"]["missing"] == 1 and day3.json()["summary"]["deactivated"] == 0
        assert (await fiona.get(f"{prefix}/auth/session")).status_code == 200
        day4 = await owner.post(
            upload,
            params={"file_name": "day4.csv", "mode": "apply"},
            content=hr_file(suffix, without_fiona, "Bavla HQ"),
            headers=owner_h,
        )
        assert day4.json()["summary"]["deactivated"] == 1, day4.text
        assert (await fiona.get(f"{prefix}/auth/session")).status_code == 401
        # The owner's manually created account is never touched by the sync.
        assert (await owner.get(f"{prefix}/auth/session")).status_code == 200
        _ = ashu_h
