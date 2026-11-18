import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import asyncssh
import httpx
import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.database import session_factory
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.communications.models import EmailDelivery
from app.domains.communications.security import decrypt_template_data
from app.domains.ideas.approval_reminders import MAX_REMINDERS, send_overdue_reminders
from app.domains.ideas.models import IdeaApprovalStage
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

PASSWORD = "Secure-sftp-reminders#2026"
SFTP_PASSWORD = "sftp-test-password"
HEADER = (
    "Username,First Name,Middle Name,Last Name,Location  Name,Department Name,"
    "Sub-Department Name,Business  Email Information Email Address,Manager User Sys ID,"
    "Manager,HOD  Job Relationships User ID,HOD  Job Relationships Name"
)


class _Server(asyncssh.SSHServer):
    auth_attempts = 0

    def begin_auth(self, username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return True

    def validate_password(self, username: str, password: str) -> bool:
        _Server.auth_attempts += 1
        return username == "hrfeed" and password == SFTP_PASSWORD


async def _start_sftp(root: Path, host_key: asyncssh.SSHKey) -> asyncssh.SSHAcceptor:
    return await asyncssh.create_server(
        _Server,
        "127.0.0.1",
        0,
        server_host_keys=[host_key],
        sftp_factory=lambda chan: asyncssh.SFTPServer(chan, chroot=str(root)),
    )


def _report(suffix: str) -> bytes:
    rows = [
        HEADER,
        f"100,Umang,,Shah,Bavla,Ops,U6,umang-{suffix}@example.com,200,,300,",
        f"200,Ravi,,Patel,Bavla,Ops,U6,ravi-{suffix}@example.com,300,,300,",
        f"300,Hema,,Rao,Bavla,Ops,U6,hema-{suffix}@example.com,,,,",
    ]
    return "\n".join(rows).encode()


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


async def _join(client: httpx.AsyncClient, tenant_id: uuid.UUID, prefix: str, email: str) -> dict:
    async with session_factory() as session, session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        delivery = await session.scalar(
            select(EmailDelivery)
            .where(EmailDelivery.recipient == email, EmailDelivery.template_key == "invitation")
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
    signed_in = await client.post(
        f"{prefix}/auth/sign-in", json={"email": email, "password": PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    return {"X-CSRF-Token": client.cookies.get(get_settings().csrf_cookie_name) or ""}


@pytest.mark.asyncio
async def test_sftp_fetch_pins_host_key_and_reminders_escalate(tmp_path: Path) -> None:
    settings = get_settings()
    original_networks = settings.hr_sftp_allowed_networks
    settings.hr_sftp_allowed_networks = "127.0.0.1/32"
    suffix = uuid.uuid4().hex[:8]
    slug = f"sftp-{suffix}"
    prefix = f"/api/v1/t/{slug}"
    owner_email = f"owner-{suffix}@example.com"
    transport = httpx.ASGITransport(app=app)
    outbound = tmp_path / "outbound"
    outbound.mkdir()
    (outbound / "hrms_report.csv").write_bytes(_report(suffix))
    (outbound / "notes.txt").write_text("ignored")
    first_key = asyncssh.generate_private_key("ssh-ed25519")
    server = await _start_sftp(tmp_path, first_key)
    port = server.sockets[0].getsockname()[1]

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")

    try:
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
                    "name": f"SFTP {suffix}",
                    "first_admin_email": owner_email,
                    "first_admin_name": "SFTP Owner",
                },
                headers={"X-CSRF-Token": platform.cookies.get(settings.csrf_cookie_name) or ""},
            )
            assert provisioned.status_code == 201, provisioned.text
            tenant_id = uuid.UUID(provisioned.json()["id"])

        async with client() as owner, client() as umang, client() as ravi:
            owner_h = await _join(owner, tenant_id, prefix, owner_email)
            sftp = f"{prefix}/admin/directory/sftp"
            await owner.put(
                f"{prefix}/admin/directory/settings",
                json={"invite_new_employees": True},
                headers=owner_h,
            )

            # Dangerous destinations are refused before any connection is made.
            for host, phrase in (("169.254.169.254", "not allowed"), ("10.1.2.3", "private")):
                await owner.put(
                    sftp,
                    json={
                        "host": host,
                        "port": 22,
                        "username": "x",
                        "secret": "y",
                        "remote_path": "/",
                    },
                    headers=owner_h,
                )
                refused = await owner.post(f"{sftp}/check-key", headers=owner_h)
                assert refused.json()["ok"] is False and phrase in refused.json()["message"]

            saved = await owner.put(
                sftp,
                json={
                    "enabled": True,
                    "host": "127.0.0.1",
                    "port": port,
                    "username": "hrfeed",
                    "auth_method": "password",
                    "secret": SFTP_PASSWORD,
                    "remote_path": "/outbound",
                },
                headers=owner_h,
            )
            view = saved.json()
            assert view["has_secret"] is True and "secret" not in view
            assert view["enabled"] is False  # cannot run until the key is trusted

            untrusted = await owner.post(f"{sftp}/fetch", headers=owner_h)
            assert untrusted.json()["ok"] is False and "trust" in untrusted.json()["message"]
            assert _Server.auth_attempts == 0

            checked = (await owner.post(f"{sftp}/check-key", headers=owner_h)).json()
            presented = checked["source"]["presented_fingerprint"]
            assert presented == first_key.get_fingerprint("sha256")
            wrong = await owner.post(
                f"{sftp}/trust-key", json={"fingerprint": "SHA256:not-the-key"}, headers=owner_h
            )
            assert wrong.status_code == 409
            trusted = await owner.post(
                f"{sftp}/trust-key", json={"fingerprint": presented}, headers=owner_h
            )
            assert trusted.json()["trusted_fingerprint"] == presented

            tested = (await owner.post(f"{sftp}/test", headers=owner_h)).json()
            assert tested["ok"] is True and "hrms_report.csv" in tested["message"]
            fetched = (await owner.post(f"{sftp}/fetch", headers=owner_h)).json()
            assert fetched["ok"] is True, fetched
            assert fetched["run"]["status"] == "applied" and fetched["run"]["summary"]["new"] == 3
            again = (await owner.post(f"{sftp}/fetch", headers=owner_h)).json()
            assert again["run"]["status"] == "duplicate"

            # Admins may run it, but only Owners change where credentials go.
            assert (await owner.get(sftp)).json()["enabled"] is False
            enable = await owner.put(
                sftp,
                json={
                    "enabled": True,
                    "host": "127.0.0.1",
                    "port": port,
                    "username": "hrfeed",
                    "remote_path": "/outbound",
                },
                headers=owner_h,
            )
            assert enable.json()["enabled"] is True and enable.json()["has_secret"] is True

            # A different server key: nothing is sent, not even the username/password.
            server.close()
            await server.wait_closed()
            attempts = _Server.auth_attempts
            server = await _start_sftp(tmp_path, asyncssh.generate_private_key("ssh-ed25519"))
            moved_port = server.sockets[0].getsockname()[1]
            await owner.put(
                sftp,
                json={
                    "enabled": True,
                    "host": "127.0.0.1",
                    "port": port,
                    "username": "hrfeed",
                    "remote_path": "/outbound",
                },
                headers=owner_h,
            )
            async with session_factory() as db, db.begin():
                await apply_tenant_to_transaction(db, tenant_id)
                from app.domains.directory.models import DirectorySftpSource

                await db.execute(
                    update(DirectorySftpSource)
                    .where(DirectorySftpSource.tenant_id == tenant_id)
                    .values(port=moved_port)
                )
            impostor = (await owner.post(f"{sftp}/fetch", headers=owner_h)).json()
            assert impostor["ok"] is False and "key has changed" in impostor["message"]
            assert _Server.auth_attempts == attempts

            # Reminders: Umang's idea waits on Ravi (his reporting manager), whose RM is Hema.
            umang_h = await _join(umang, tenant_id, prefix, f"umang-{suffix}@example.com")
            await _join(ravi, tenant_id, prefix, f"ravi-{suffix}@example.com")
            workflow = (
                await owner.get(f"{prefix}/admin/configuration/workflows/contracts")
            ).json()[0]
            draft = await owner.post(
                f"{prefix}/admin/configuration/workflows/{workflow['id']}/versions",
                json={
                    "stages": [
                        {
                            "key": "rm",
                            "name": "Reporting manager",
                            "source": "dynamic",
                            "relationship": "reporting_manager",
                            "sla_hours": 24,
                        }
                    ]
                },
                headers=owner_h,
            )
            await owner.post(
                f"{prefix}/admin/configuration/workflows/{workflow['id']}/versions/{draft.json()['id']}/publish",
                headers=owner_h,
            )
            # Accounts created after the first sync link on the next HR file.
            async with session_factory() as db, db.begin():
                await apply_tenant_to_transaction(db, tenant_id)
                await db.execute(
                    update(DirectorySftpSource)
                    .where(DirectorySftpSource.tenant_id == tenant_id)
                    .values(port=port)
                )
            server.close()
            await server.wait_closed()
            server = await _start_sftp(tmp_path, first_key)
            await owner.put(
                sftp,
                json={
                    "enabled": True,
                    "host": "127.0.0.1",
                    "port": server.sockets[0].getsockname()[1],
                    "username": "hrfeed",
                    "remote_path": "/outbound",
                },
                headers=owner_h,
            )
            await owner.post(f"{sftp}/check-key", headers=owner_h)
            await owner.post(f"{sftp}/trust-key", json={"fingerprint": presented}, headers=owner_h)
            (outbound / "hrms_report.csv").write_bytes(
                _report(suffix).replace(b"Bavla", b"Bavla HQ")
            )
            relinked = (await owner.post(f"{sftp}/fetch", headers=owner_h)).json()
            assert relinked["run"]["status"] == "applied", relinked

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
                "title": "Label printers on every line",
                "problem_statement": "Labels are hand-written.",
                "business_case": "Fewer errors.",
                "current_state": "Manual",
                "target_state": "Printed",
                "impacts": ["quality"],
                "estimated_annual_saving": "20000",
            }
            idea = (await umang.post(f"{prefix}/ideas", json=command, headers=umang_h)).json()
            submitted = await umang.post(
                f"{prefix}/ideas/{idea['id']}/submit", json=command, headers=umang_h
            )
            assert submitted.status_code == 200, submitted.text

            now = datetime.now(UTC)
            async with session_factory() as db, db.begin():
                await apply_tenant_to_transaction(db, tenant_id)
                await db.execute(
                    update(IdeaApprovalStage)
                    .where(
                        IdeaApprovalStage.idea_id == uuid.UUID(idea["id"]),
                        IdeaApprovalStage.status == "pending",
                    )
                    .values(due_at=now - timedelta(hours=2))
                )
            ravi_email, hema_email = f"ravi-{suffix}@example.com", f"hema-{suffix}@example.com"
            for day in range(MAX_REMINDERS + 1):
                async with session_factory() as session:
                    await send_overdue_reminders(
                        tenant_id, settings, session, now=now + timedelta(days=day)
                    )
                # Running twice at the same moment never sends twice.
                async with session_factory() as session:
                    await send_overdue_reminders(
                        tenant_id, settings, session, now=now + timedelta(days=day)
                    )
            assert (await _mail(tenant_id, ravi_email)).count("approval_overdue") == MAX_REMINDERS
            assert (await _mail(tenant_id, hema_email)).count("approval_escalation") == 1
    finally:
        settings.hr_sftp_allowed_networks = original_networks
        server.close()
        await server.wait_closed()
