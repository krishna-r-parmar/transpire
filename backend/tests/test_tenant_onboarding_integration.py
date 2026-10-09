import os
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import delete, func, select, update

from app.core.config import get_settings
from app.core.database import session_factory
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.communications.models import EmailDelivery, EmailDeliveryStatus
from app.domains.communications.security import decrypt_template_data
from app.domains.identity.models import GlobalAuthenticationThrottle, User
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


@pytest.mark.asyncio
async def test_platform_provisioning_invitation_and_tenant_admin_journey() -> None:
    settings = get_settings()
    suffix = uuid.uuid4().hex[:8]
    tenant_slug = f"journey-{suffix}"
    tenant_prefix = f"/api/v1/t/{tenant_slug}"
    platform_prefix = f"/api/v1/t/{settings.development_tenant_slug}"
    administrator_email = f"admin-{suffix}@example.com"
    administrator_password = "Secure-tenant-password#2026"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        signed_in = await client.post(
            f"{platform_prefix}/auth/sign-in",
            json={
                "email": str(settings.development_admin_email),
                "password": settings.development_admin_password.get_secret_value(),
            },
        )
        assert signed_in.status_code == 200
        assert signed_in.json()["session"]["user"]["is_platform_admin"] is True

        command = {
            "slug": tenant_slug,
            "name": f"Journey {suffix}",
            "first_admin_email": administrator_email,
            "first_admin_name": "Journey Administrator",
        }
        rejected_without_csrf = await client.post(f"{platform_prefix}/platform/tenants", json=command)
        assert rejected_without_csrf.status_code == 403

        csrf_token = client.cookies.get(settings.csrf_cookie_name)
        assert csrf_token
        provisioned = await client.post(
            f"{platform_prefix}/platform/tenants",
            json=command,
            headers={"X-CSRF-Token": csrf_token},
        )
        assert provisioned.status_code == 201, provisioned.text
        tenant_id = provisioned.json()["id"]

        listed = await client.get(f"{platform_prefix}/platform/tenants")
        assert listed.status_code == 200
        listed_tenant = next(tenant for tenant in listed.json() if tenant["id"] == tenant_id)
        assert listed_tenant["invitation"]["email"] == administrator_email

        unknown_email = f"unknown-{suffix}@example.com"
        for _ in range(settings.sign_in_rate_limit):
            denied = await client.post(
                f"{platform_prefix}/auth/sign-in",
                json={"email": unknown_email, "password": "wrong-password"},
            )
            assert denied.status_code == 401
        throttled = await client.post(
            f"{platform_prefix}/auth/sign-in",
            json={"email": unknown_email, "password": "wrong-password"},
        )
        assert throttled.status_code == 429
        assert int(throttled.headers["Retry-After"]) > 0

    async with session_factory() as session:
        delivery = await session.scalar(
            select(EmailDelivery)
            .where(
                EmailDelivery.tenant_id == uuid.UUID(tenant_id),
                EmailDelivery.template_key == "invitation",
            )
            .order_by(EmailDelivery.created_at.desc())
            .limit(1)
        )
    assert delivery is not None
    assert "action_url" not in delivery.template_data
    assert delivery.encrypted_template_data is not None
    secure_data = decrypt_template_data(delivery.encrypted_template_data, settings)
    invitation_token = parse_qs(urlparse(str(secure_data["action_url"])).query)["token"][0]

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://localhost",
    ) as tenant_client:
        inspected = await tenant_client.post(
            "http://localhost/api/v1/auth/invitations/inspect",
            json={"token": invitation_token},
        )
        assert inspected.status_code == 200, inspected.text
        assert inspected.json()["requires_password"] is True
        assert inspected.json()["sign_in_url"] == f"http://localhost:3000/t/{tenant_slug}/sign-in"

        accepted = await tenant_client.post(
            "http://localhost/api/v1/auth/invitations/accept",
            json={"token": invitation_token, "new_password": administrator_password},
        )
        reused = await tenant_client.post(
            "http://localhost/api/v1/auth/invitations/accept",
            json={"token": invitation_token, "new_password": administrator_password},
        )
        assert accepted.status_code == 200, accepted.text
        assert reused.status_code == 400

        tenant_sign_in = await tenant_client.post(
            f"{tenant_prefix}/auth/sign-in",
            json={"email": administrator_email, "password": administrator_password},
        )
        assert tenant_sign_in.status_code == 200, tenant_sign_in.text
        assert "tenant_admin" in tenant_sign_in.json()["session"]["roles"]
        assert tenant_sign_in.json()["session"]["user"]["is_platform_admin"] is False

        platform_boundary = await tenant_client.get(f"{platform_prefix}/platform/tenants")
        assert platform_boundary.status_code == 401

        tenant_csrf = tenant_client.cookies.get(settings.csrf_cookie_name)
        assert tenant_csrf
        workflow_contracts = await tenant_client.get(
            f"{tenant_prefix}/admin/configuration/workflows/contracts"
        )
        assert workflow_contracts.status_code == 200, workflow_contracts.text
        idea_approval = workflow_contracts.json()[0]
        assert idea_approval["key"] == "idea_approval"
        assert idea_approval["versions"][0]["status"] == "published"
        assert idea_approval["versions"][0]["stages"][0]["name"] == "Demo Approval"

        site = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/master-data/site",
            json={"code": "main_site", "name": "Main Site"},
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert site.status_code == 201, site.text
        second_site = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/master-data/site",
            json={"code": "second_site", "name": "Second Site"},
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert second_site.status_code == 201, second_site.text
        department_without_site = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/master-data/department",
            json={"code": "quality", "name": "Quality"},
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert department_without_site.status_code == 409
        department = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/master-data/department",
            json={
                "code": "quality",
                "name": "Quality",
                "site_ids": [site.json()["id"], second_site.json()["id"]],
            },
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert department.status_code == 201, department.text
        assert set(department.json()["site_ids"]) == {site.json()["id"], second_site.json()["id"]}
        common_department = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/master-data/department",
            json={
                "code": "shared_services",
                "name": "Shared Services",
                "applies_to_all_sites": True,
            },
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert common_department.status_code == 201, common_department.text
        assert common_department.json()["applies_to_all_sites"] is True
        category = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/master-data/category",
            json={"code": "safety", "name": "Safety"},
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert category.status_code == 201, category.text
        subcategory = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/master-data/subcategory",
            json={
                "code": "ergonomics",
                "name": "Ergonomics",
                "parent_id": category.json()["id"],
            },
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert subcategory.status_code == 201, subcategory.text
        process_area = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/master-data/process_area",
            json={"code": "packaging", "name": "Packaging"},
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert process_area.status_code == 201, process_area.text

        workflow_assignees = await tenant_client.get(
            f"{tenant_prefix}/admin/configuration/workflows/assignees"
        )
        assert workflow_assignees.status_code == 200, workflow_assignees.text
        administrator_assignee = next(
            assignee
            for assignee in workflow_assignees.json()
            if assignee["email"] == administrator_email
        )
        assert administrator_assignee["status"] == "active"

        workflow_draft = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/workflows/{idea_approval['id']}/versions",
            json={
                "stages": [
                    {
                        "key": "department_review",
                        "name": "Department Review",
                        "assignee_membership_id": administrator_assignee["membership_id"],
                        "sla_hours": 24,
                        "required": True,
                    },
                    {
                        "key": "final_approval",
                        "name": "Final Approval",
                        "assignee_membership_id": administrator_assignee["membership_id"],
                        "sla_hours": 48,
                        "required": True,
                    },
                ]
            },
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert workflow_draft.status_code == 201, workflow_draft.text
        assert workflow_draft.json()["version"] == 2
        assert workflow_draft.json()["stages"][0]["assignee_email"] == administrator_email
        published = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/workflows/{idea_approval['id']}/versions/{workflow_draft.json()['id']}/publish",
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert published.status_code == 204, published.text
        versioned_contract = (
            await tenant_client.get(f"{tenant_prefix}/admin/configuration/workflows/contracts")
        ).json()[0]
        assert versioned_contract["versions"][0]["status"] == "published"
        assert versioned_contract["versions"][0]["version"] == 2
        assert versioned_contract["versions"][1]["status"] == "retired"

        idea_command = {
            "idea_type": "kaizen",
            "category_id": category.json()["id"],
            "subcategory_id": subcategory.json()["id"],
            "process_area_id": process_area.json()["id"],
            "title": "Reduce repetitive packaging checks",
            "problem_statement": "Manual checks create delays during every packaging batch.",
            "business_case": "Standardise the check and capture results digitally.",
            "current_state": "18 minutes per batch",
            "target_state": "8 minutes per batch",
            "impacts": ["delivery", "productivity"],
            "estimated_annual_saving": "250000",
        }
        disposable_draft = await tenant_client.post(
            f"{tenant_prefix}/ideas",
            json={**idea_command, "title": "Disposable discovery draft", "draft_step": 3},
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert disposable_draft.status_code == 201, disposable_draft.text
        editable_draft = await tenant_client.get(
            f"{tenant_prefix}/ideas/{disposable_draft.json()['id']}/edit"
        )
        assert editable_draft.status_code == 200, editable_draft.text
        assert editable_draft.json()["status"] == "draft"
        assert editable_draft.json()["draft_step"] == 3
        draft_home = await tenant_client.get(f"{tenant_prefix}/ideas/home-summary")
        discovered_draft = next(
            idea
            for idea in draft_home.json()["ideas"]
            if idea["id"] == disposable_draft.json()["id"]
        )
        assert discovered_draft["can_edit_idea"] is True
        assert discovered_draft["can_delete_draft"] is True
        deleted_draft = await tenant_client.delete(
            f"{tenant_prefix}/ideas/{disposable_draft.json()['id']}",
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert deleted_draft.status_code == 204, deleted_draft.text
        assert (
            await tenant_client.get(f"{tenant_prefix}/ideas/{disposable_draft.json()['id']}/edit")
        ).status_code == 404

        draft_idea = await tenant_client.post(
            f"{tenant_prefix}/ideas",
            json=idea_command,
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert draft_idea.status_code == 201, draft_idea.text
        submitted_idea = await tenant_client.post(
            f"{tenant_prefix}/ideas/{draft_idea.json()['id']}/submit",
            json=idea_command,
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert submitted_idea.status_code == 200, submitted_idea.text
        idea_bank = await tenant_client.get(f"{tenant_prefix}/ideas")
        assert idea_bank.status_code == 200, idea_bank.text
        assert idea_bank.json()[0]["title"] == idea_command["title"]
        assert idea_bank.json()[0]["problem_statement"] is None
        assert idea_bank.json()[0]["estimated_annual_saving"] is None

        full_policy = await tenant_client.put(
            f"{tenant_prefix}/admin/configuration/idea-bank-policy",
            json={
                "detail_level": "full",
                "show_contributor": False,
                "show_financials": True,
            },
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert full_policy.status_code == 200, full_policy.text
        full_idea_bank = await tenant_client.get(f"{tenant_prefix}/ideas")
        assert full_idea_bank.status_code == 200
        assert full_idea_bank.json()[0]["problem_statement"] == idea_command["problem_statement"]
        assert full_idea_bank.json()[0]["contributor"] is None
        assert full_idea_bank.json()[0]["estimated_annual_saving"] == "250000.00"

        submitted_detail = await tenant_client.get(
            f"{tenant_prefix}/ideas/{draft_idea.json()['id']}"
        )
        assert submitted_detail.status_code == 200, submitted_detail.text
        first_stage = next(
            stage for stage in submitted_detail.json()["approval_stages"] if stage["is_actionable"]
        )
        correction = await tenant_client.post(
            f"{tenant_prefix}/ideas/{draft_idea.json()['id']}/approvals/{first_stage['id']}",
            json={
                "decision": "needs_correction",
                "comment": "Clarify the measured improvement target.",
            },
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert correction.status_code == 200, correction.text
        assert correction.json()["status"] == "needs_correction"
        correction_edit = await tenant_client.get(
            f"{tenant_prefix}/ideas/{draft_idea.json()['id']}/edit"
        )
        assert correction_edit.status_code == 200, correction_edit.text
        assert correction_edit.json()["correction_reason"] == (
            "Clarify the measured improvement target."
        )
        correction_home = await tenant_client.get(f"{tenant_prefix}/ideas/home-summary")
        correction_summary = next(
            idea
            for idea in correction_home.json()["ideas"]
            if idea["id"] == draft_idea.json()["id"]
        )
        assert correction_summary["can_edit_idea"] is True
        assert correction_summary["can_delete_draft"] is False
        assert correction_summary["correction_reason"] == (
            "Clarify the measured improvement target."
        )
        corrected_command = {
            **idea_command,
            "target_state": "8 measured minutes per packaging batch",
        }
        saved_correction = await tenant_client.put(
            f"{tenant_prefix}/ideas/{draft_idea.json()['id']}",
            json=corrected_command,
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert saved_correction.status_code == 200, saved_correction.text
        assert saved_correction.json()["status"] == "needs_correction"
        resubmitted = await tenant_client.post(
            f"{tenant_prefix}/ideas/{draft_idea.json()['id']}/resubmit",
            json=corrected_command,
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert resubmitted.status_code == 200, resubmitted.text
        assert resubmitted.json()["status"] == "submitted"
        resubmitted_detail = await tenant_client.get(
            f"{tenant_prefix}/ideas/{draft_idea.json()['id']}"
        )
        assert resubmitted_detail.status_code == 200, resubmitted_detail.text
        rounds = resubmitted_detail.json()["approval_stages"]
        assert {stage["round_number"] for stage in rounds} == {1, 2}
        assert next(stage for stage in rounds if stage["round_number"] == 1)["status"] == (
            "needs_correction"
        )
        assert next(
            stage
            for stage in rounds
            if stage["round_number"] == 2 and stage["stage_order"] == 1
        )["status"] == "pending"
        tenant_audit = await tenant_client.get(f"{tenant_prefix}/audit/events?page_size=100")
        assert tenant_audit.status_code == 200, tenant_audit.text
        assert tenant_audit.json()["tenant_scope"] is True
        audit_types = {event["event_type"] for event in tenant_audit.json()["items"]}
        assert {
            "idea.draft_created",
            "idea.draft_deleted",
            "idea.submitted",
            "idea.approval_needs_correction",
            "idea.correction_updated",
            "idea.resubmitted",
            "workflow.version_created",
            "workflow.version_published",
        }.issubset(audit_types)

        roles = await tenant_client.get(f"{tenant_prefix}/admin/roles")
        members = await tenant_client.get(f"{tenant_prefix}/admin/members")
        invited = await tenant_client.post(
            f"{tenant_prefix}/admin/invitations",
            json={
                "email": f"member-{suffix}@example.com",
                "display_name": "Journey Member",
                "role_key": "idea_submitter",
            },
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert roles.status_code == 200
        assert {role["key"] for role in roles.json()} == {"tenant_admin", "idea_submitter"}
        assert members.status_code == 200
        assert members.json()[0]["email"] == administrator_email
        assert invited.status_code == 202, invited.text
        assignable_after_invite = await tenant_client.get(
            f"{tenant_prefix}/admin/configuration/workflows/assignees"
        )
        pending_assignee = next(
            assignee
            for assignee in assignable_after_invite.json()
            if assignee["email"] == f"member-{suffix}@example.com"
        )
        assert pending_assignee["status"] == "pending"
        pending_workflow_draft = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/workflows/{idea_approval['id']}/versions",
            json={
                "stages": [
                    {
                        "key": "pending_person_review",
                        "name": "Pending Person Review",
                        "assignee_membership_id": pending_assignee["membership_id"],
                        "sla_hours": 24,
                        "required": True,
                    }
                ]
            },
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert pending_workflow_draft.status_code == 201, pending_workflow_draft.text

        invitations = await tenant_client.get(f"{tenant_prefix}/admin/invitations")
        assert invitations.status_code == 200
        member_invitation = next(
            item for item in invitations.json() if item["email"] == f"member-{suffix}@example.com"
        )
        resent = await tenant_client.post(
            f"{tenant_prefix}/admin/invitations/{member_invitation['id']}/resend",
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert resent.status_code == 202, resent.text
        resent_id = resent.json()["id"]
        revoked = await tenant_client.delete(
            f"{tenant_prefix}/admin/invitations/{resent_id}",
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert revoked.status_code == 204
        assignable_after_revoke = await tenant_client.get(
            f"{tenant_prefix}/admin/configuration/workflows/assignees"
        )
        assert all(
            assignee["email"] != f"member-{suffix}@example.com"
            for assignee in assignable_after_revoke.json()
        )
        rejected_publish = await tenant_client.post(
            f"{tenant_prefix}/admin/configuration/workflows/{idea_approval['id']}/versions/{pending_workflow_draft.json()['id']}/publish",
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert rejected_publish.status_code == 409, rejected_publish.text
        async with session_factory() as session:
            queued_after_revoke = await session.scalar(
                select(func.count())
                .select_from(EmailDelivery)
                .where(
                    EmailDelivery.tenant_id == uuid.UUID(tenant_id),
                    EmailDelivery.recipient == f"member-{suffix}@example.com",
                    EmailDelivery.template_key == "invitation",
                    EmailDelivery.status == EmailDeliveryStatus.QUEUED,
                )
            )
        assert queued_after_revoke == 0
        resent_after_revoke = await tenant_client.post(
            f"{tenant_prefix}/admin/invitations/{resent_id}/resend",
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert resent_after_revoke.status_code == 202, resent_after_revoke.text

        async with session_factory() as session:
            member_delivery = await session.scalar(
                select(EmailDelivery)
                .where(
                    EmailDelivery.tenant_id == uuid.UUID(tenant_id),
                    EmailDelivery.recipient == f"member-{suffix}@example.com",
                    EmailDelivery.template_key == "invitation",
                )
                .order_by(EmailDelivery.created_at.desc())
                .limit(1)
            )
            queued_after_resend = await session.scalar(
                select(func.count())
                .select_from(EmailDelivery)
                .where(
                    EmailDelivery.tenant_id == uuid.UUID(tenant_id),
                    EmailDelivery.recipient == f"member-{suffix}@example.com",
                    EmailDelivery.template_key == "invitation",
                    EmailDelivery.status == EmailDeliveryStatus.QUEUED,
                )
            )
        assert member_delivery is not None
        assert queued_after_resend == 1
        assert member_delivery.encrypted_template_data is not None
        member_secure_data = decrypt_template_data(
            member_delivery.encrypted_template_data, settings
        )
        member_token = parse_qs(urlparse(str(member_secure_data["action_url"])).query)["token"][0]
        member_password = "Secure-member-password#2026"
        member_accepted = await tenant_client.post(
            "http://localhost/api/v1/auth/invitations/accept",
            json={"token": member_token, "new_password": member_password},
        )
        assert member_accepted.status_code == 200, member_accepted.text

        async with httpx.AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as member_client:
            member_login = await member_client.post(
                f"{tenant_prefix}/auth/sign-in",
                json={
                    "email": f"member-{suffix}@example.com",
                    "password": member_password,
                },
            )
            assert member_login.status_code == 200
            member_csrf = member_client.cookies.get(settings.csrf_cookie_name)
            assert member_csrf
            member_draft = await member_client.post(
                f"{tenant_prefix}/ideas",
                json={**idea_command, "title": "Member account audit draft", "draft_step": 2},
                headers={"X-CSRF-Token": member_csrf},
            )
            assert member_draft.status_code == 201, member_draft.text
            member_audit = await member_client.get(f"{tenant_prefix}/audit/events")
            assert member_audit.status_code == 200, member_audit.text
            assert member_audit.json()["tenant_scope"] is False
            assert member_audit.json()["total"] == 1
            assert member_audit.json()["items"][0]["event_type"] == "idea.draft_created"
            assert member_audit.json()["items"][0]["actor_email"] == (
                f"member-{suffix}@example.com"
            )
            refreshed_members = await tenant_client.get(f"{tenant_prefix}/admin/members")
            member = next(
                item
                for item in refreshed_members.json()
                if item["email"] == f"member-{suffix}@example.com"
            )
            deactivated = await tenant_client.patch(
                f"{tenant_prefix}/admin/members/{member['id']}/status",
                json={"status": "inactive"},
                headers={"X-CSRF-Token": tenant_csrf},
            )
            assert deactivated.status_code == 204
            assert (await member_client.get(f"{tenant_prefix}/auth/session")).status_code == 401
            reactivated = await tenant_client.patch(
                f"{tenant_prefix}/admin/members/{member['id']}/status",
                json={"status": "active"},
                headers={"X-CSRF-Token": tenant_csrf},
            )
            assert reactivated.status_code == 204

        for _ in range(settings.account_lockout_attempts):
            failed = await tenant_client.post(
                f"{tenant_prefix}/auth/sign-in",
                json={"email": administrator_email, "password": "wrong-password"},
            )
            assert failed.status_code == 401
        locked = await tenant_client.post(
            f"{tenant_prefix}/auth/sign-in",
            json={"email": administrator_email, "password": administrator_password},
        )
        assert locked.status_code == 401

        async with session_factory() as session, session.begin():
            await apply_tenant_to_transaction(session, uuid.UUID(tenant_id))
            user_id = await session.scalar(select(User.id).where(User.email == administrator_email))
            assert user_id is not None
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.execute(delete(GlobalAuthenticationThrottle))

        unlocked = await tenant_client.post(
            f"{tenant_prefix}/auth/sign-in",
            json={"email": administrator_email, "password": administrator_password},
        )
        assert unlocked.status_code == 200
        tenant_csrf = tenant_client.cookies.get(settings.csrf_cookie_name)
        assert tenant_csrf

        multi_tenant_invitation = await tenant_client.post(
            f"{tenant_prefix}/admin/invitations",
            json={
                "email": str(settings.development_admin_email),
                "display_name": settings.development_admin_name,
                "role_key": "idea_submitter",
            },
            headers={"X-CSRF-Token": tenant_csrf},
        )
        assert multi_tenant_invitation.status_code == 202, multi_tenant_invitation.text

        async with session_factory() as session:
            multi_tenant_delivery = await session.scalar(
                select(EmailDelivery)
                .where(
                    EmailDelivery.tenant_id == uuid.UUID(tenant_id),
                    EmailDelivery.recipient == str(settings.development_admin_email),
                    EmailDelivery.template_key == "invitation",
                )
                .order_by(EmailDelivery.created_at.desc())
                .limit(1)
            )
        assert multi_tenant_delivery is not None
        assert multi_tenant_delivery.encrypted_template_data is not None
        multi_tenant_secure_data = decrypt_template_data(
            multi_tenant_delivery.encrypted_template_data, settings
        )
        multi_tenant_token = parse_qs(
            urlparse(str(multi_tenant_secure_data["action_url"])).query
        )["token"][0]
        accepted_existing_account = await tenant_client.post(
            "/api/v1/auth/invitations/accept",
            json={"token": multi_tenant_token},
        )
        assert accepted_existing_account.status_code == 200, accepted_existing_account.text

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as chooser:
        central_login = await chooser.post(
            "/api/v1/auth/sign-in",
            json={
                "email": str(settings.development_admin_email),
                "password": settings.development_admin_password.get_secret_value(),
            },
        )
        assert central_login.status_code == 200, central_login.text
        discovery = central_login.json()
        assert discovery["selection_required"] is True
        assert discovery["session"] is None
        assert {workspace["slug"] for workspace in discovery["workspaces"]} >= {
            settings.development_tenant_slug,
            tenant_slug,
        }
        selection_token = discovery["selection_token"]
        selected = await chooser.post(
            "/api/v1/auth/select-workspace",
            json={"selection_token": selection_token, "tenant_id": tenant_id},
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["session"]["tenant"]["slug"] == tenant_slug
        replayed = await chooser.post(
            "/api/v1/auth/select-workspace",
            json={"selection_token": selection_token, "tenant_id": tenant_id},
        )
        assert replayed.status_code == 400
        assert (await chooser.get(f"{tenant_prefix}/auth/session")).status_code == 200

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        signed_in = await client.post(
            f"{platform_prefix}/auth/sign-in",
            json={
                "email": str(settings.development_admin_email),
                "password": settings.development_admin_password.get_secret_value(),
            },
        )
        assert signed_in.status_code == 200
        platform_csrf = client.cookies.get(settings.csrf_cookie_name)
        assert platform_csrf
        suspended = await client.patch(
            f"{platform_prefix}/platform/tenants/{tenant_id}/status",
            json={"status": "suspended"},
            headers={"X-CSRF-Token": platform_csrf},
        )
        assert suspended.status_code == 204
        async with httpx.AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as unavailable_client:
            assert (await unavailable_client.get(f"{tenant_prefix}/auth/session")).status_code == 403
        activated = await client.patch(
            f"{platform_prefix}/platform/tenants/{tenant_id}/status",
            json={"status": "active"},
            headers={"X-CSRF-Token": platform_csrf},
        )
        assert activated.status_code == 204
        platform_members = await client.get(f"{platform_prefix}/platform/tenants/{tenant_id}/members")
        assert platform_members.status_code == 200
        managed_member = next(
            item
            for item in platform_members.json()
            if item["email"] == f"member-{suffix}@example.com"
        )
        platform_deactivated = await client.patch(
            f"{platform_prefix}/platform/tenants/{tenant_id}/members/{managed_member['id']}/status",
            json={"status": "inactive"},
            headers={"X-CSRF-Token": platform_csrf},
        )
        assert platform_deactivated.status_code == 204
        platform_reactivated = await client.patch(
            f"{platform_prefix}/platform/tenants/{tenant_id}/members/{managed_member['id']}/status",
            json={"status": "active"},
            headers={"X-CSRF-Token": platform_csrf},
        )
        assert platform_reactivated.status_code == 204
        removed = await client.delete(
            f"{platform_prefix}/platform/tenants/{tenant_id}",
            headers={"X-CSRF-Token": platform_csrf},
        )
        assert removed.status_code == 204
        tenants = await client.get(f"{platform_prefix}/platform/tenants")
        removed_tenant = next(item for item in tenants.json() if item["id"] == tenant_id)
        assert removed_tenant["status"] == "removed"
        async with httpx.AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as removed_client:
                assert (await removed_client.get(f"{tenant_prefix}/auth/session")).status_code == 403
