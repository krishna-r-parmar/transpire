"""Apply an HR employee report to the workspace, idempotently and safely.

Idempotency works at three levels:
- file: a SHA-256 of the file; a file already applied is recorded as a duplicate and skipped.
- row: each employee's normalised fields are hashed; unchanged rows cause no writes.
- effect: invitations, deactivations and approval re-routing are driven by state, so
  re-running the same file (for example after a crash) changes nothing further.

Guards against the classic HR-sync failures: a truncated file never deactivates people
(large drops are blocked unless forced), an employee must be absent from two consecutive
files before access is removed, accounts created by hand are never deactivated, roles are
never changed, and a workspace always keeps one active Workspace Owner.
"""

import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.audit.controllers import record_audit_event
from app.domains.configuration.models import WorkflowVersion
from app.domains.directory.models import DirectoryEmployee, DirectoryRun
from app.domains.directory.parser import EmployeeRow, ReportFormatError, parse_report
from app.domains.directory.schemas import DirectoryRunSummary, DirectorySettings
from app.domains.ideas.approval_notifications import dispatch_approval_notifications
from app.domains.ideas.approval_routing import activate_next_step, reroute_pending
from app.domains.ideas.models import Idea, IdeaApprovalStage, IdeaStatus
from app.domains.identity.access import CONTRIBUTOR
from app.domains.identity.models import InvitationToken, Membership, MembershipStatus, User
from app.domains.identity.repositories import SQLAlchemyIdentityRepository
from app.domains.identity.schemas import SessionIdentity
from app.domains.tenants.models import Tenant
from app.domains.tenants.repositories import SQLAlchemyTenantRepository

LEAVE_AFTER_MISSING_RUNS = 2
MAX_INVITES_PER_RUN = 500
REPORT_LIST_LIMIT = 200
SETTLE_SECONDS = 60

tenant_repository = SQLAlchemyTenantRepository()
identity_repository = SQLAlchemyIdentityRepository()


class DirectoryRunBlocked(Exception):
    pass


@dataclass
class Plan:
    new: list[EmployeeRow] = field(default_factory=list)
    changed: list[tuple[EmployeeRow, DirectoryEmployee, list[str]]] = field(default_factory=list)
    returning: list[EmployeeRow] = field(default_factory=list)
    unchanged: int = 0
    newly_missing: list[DirectoryEmployee] = field(default_factory=list)
    leaving: list[DirectoryEmployee] = field(default_factory=list)


def read_settings(tenant: Tenant) -> DirectorySettings:
    return DirectorySettings.model_validate((tenant.settings or {}).get("hr_directory", {}))


def _domain_allowed(email: str, settings: DirectorySettings) -> bool:
    if not settings.allowed_email_domains:
        return True
    domain = email.rsplit("@", 1)[-1]
    return any(
        domain == allowed or domain.endswith(f".{allowed}")
        for allowed in settings.allowed_email_domains
    )


def _plan(rows: list[EmployeeRow], existing: dict[str, DirectoryEmployee]) -> Plan:
    plan = Plan()
    present = set()
    for row in rows:
        present.add(row.employee_id)
        record = existing.get(row.employee_id)
        if record is None:
            plan.new.append(row)
        elif record.status != "active":
            plan.returning.append(row)
        elif record.row_hash != row.row_hash:
            fields = [
                name
                for name in (
                    "first_name",
                    "middle_name",
                    "last_name",
                    "email",
                    "location",
                    "department",
                    "sub_department",
                    "manager_employee_id",
                    "hod_employee_id",
                )
                if (getattr(record, name) or None) != (getattr(row, name) or None)
            ]
            plan.changed.append((row, record, fields))
        else:
            plan.unchanged += 1
    for employee_id, record in existing.items():
        if employee_id in present or record.status == "left":
            continue
        if record.missing_runs + 1 >= LEAVE_AFTER_MISSING_RUNS:
            plan.leaving.append(record)
        else:
            plan.newly_missing.append(record)
    return plan


def _people(rows: list[EmployeeRow] | list[DirectoryEmployee]) -> list[dict[str, str]]:
    return [
        {"employee_id": row.employee_id, "name": row.display_name}
        for row in rows[:REPORT_LIST_LIMIT]
    ]


def _summary(run: DirectoryRun) -> DirectoryRunSummary:
    return DirectoryRunSummary(
        id=run.id,
        file_name=run.file_name,
        source=run.source,
        status=run.status,
        created_at=run.created_at,
        summary=run.summary,
        report=run.report,
    )


async def _members_by_email(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, tuple[Membership, User]]:
    rows = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id)
        )
    ).all()
    return {user.email.casefold(): (membership, user) for membership, user in rows}


async def _deactivate(
    session: AsyncSession, tenant_id: uuid.UUID, membership: Membership, user: User, now: datetime
) -> str | None:
    """Remove access for a leaver. Returns a reason when it was not safe to do so."""
    from app.domains.tenants.controllers import _discard_queued_invitation_emails

    owners = await tenant_repository.lock_active_owner_membership_ids(session, tenant_id)
    if membership.id in owners and len(owners) <= 1:
        return "is the last active Workspace Owner"
    membership.status = MembershipStatus.INACTIVE
    await identity_repository.revoke_user_sessions(session, tenant_id, user.id, now)
    await session.execute(
        update(InvitationToken)
        .where(
            InvitationToken.tenant_id == tenant_id,
            InvitationToken.email == user.email,
            InvitationToken.accepted_at.is_(None),
            InvitationToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await _discard_queued_invitation_emails(session, tenant_id, recipient=user.email)
    return None


async def reroute_open_approvals(
    session: AsyncSession, tenant_id: uuid.UUID, settings: Settings, now: datetime
) -> list[str]:
    """Re-resolve the active step of every idea awaiting approval."""
    from app.domains.ideas.controllers import complete_approval

    notes: list[str] = []
    ideas = (
        await session.scalars(
            select(Idea)
            .where(
                Idea.tenant_id == tenant_id,
                Idea.status == IdeaStatus.SUBMITTED,
                Idea.id.in_(
                    select(IdeaApprovalStage.idea_id).where(
                        IdeaApprovalStage.tenant_id == tenant_id,
                        IdeaApprovalStage.status == "pending",
                    )
                ),
            )
            .with_for_update()
        )
    ).all()
    for idea in ideas:
        version = (
            await session.get(WorkflowVersion, idea.workflow_version_id)
            if idea.workflow_version_id
            else None
        )
        if version is None:
            continue
        result = await reroute_pending(session, idea, version, now)
        notes.extend(result.notes)
        if result.step_skipped_at is not None:
            round_number = await session.scalar(
                select(IdeaApprovalStage.round_number)
                .where(
                    IdeaApprovalStage.tenant_id == tenant_id, IdeaApprovalStage.idea_id == idea.id
                )
                .order_by(IdeaApprovalStage.round_number.desc())
                .limit(1)
            )
            if not await activate_next_step(
                session,
                idea,
                version,
                int(round_number or 1),
                after_order=result.step_skipped_at,
                now=now,
            ):
                await complete_approval(session, tenant_id, idea, settings)
                notes.append(f"{idea.reference}: no further approvers, approval completed.")
        if result.notes:
            await dispatch_approval_notifications(session, idea, settings)
    return notes


async def run_directory_sync(
    *,
    tenant_id: uuid.UUID,
    content: bytes,
    file_name: str,
    source: str,
    actor: SessionIdentity | None,
    settings: Settings,
    session: AsyncSession,
    apply: bool,
    force: bool = False,
    file_mtime: float | None = None,
) -> DirectoryRunSummary:
    from app.domains.tenants.controllers import _queue_invitation

    now = datetime.now(UTC)
    sha = hashlib.sha256(content).hexdigest()
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"directory:{tenant_id}"}
        )
        tenant = await session.get(Tenant, tenant_id)
        assert tenant is not None
        options = read_settings(tenant)

        def record(
            status: str, summary: dict[str, object], report: dict[str, object]
        ) -> DirectoryRun:
            run = DirectoryRun(
                tenant_id=tenant_id,
                file_name=file_name[:255],
                file_sha256=sha,
                source=source,
                status=status,
                summary=summary,
                report=report,
                actor_user_id=actor.user.id if actor else None,
                created_at=now,
            )
            session.add(run)
            return run

        last_applied = await session.scalar(
            select(DirectoryRun)
            .where(DirectoryRun.tenant_id == tenant_id, DirectoryRun.status == "applied")
            .order_by(DirectoryRun.created_at.desc())
            .limit(1)
        )
        if apply and await session.scalar(
            select(DirectoryRun.id).where(
                DirectoryRun.tenant_id == tenant_id,
                DirectoryRun.file_sha256 == sha,
                DirectoryRun.status == "applied",
            )
        ):
            run = record("duplicate", {}, {"message": "This exact file was already applied."})
            await session.flush()
            return _summary(run)
        if (
            apply
            and file_mtime is not None
            and last_applied is not None
            and float(last_applied.summary.get("file_mtime") or 0) > file_mtime
        ):
            run = record(
                "rejected",
                {"file_mtime": file_mtime},
                {"message": "This file is older than the last applied HR file, so it was ignored."},
            )
            await session.flush()
            return _summary(run)

        try:
            parsed = parse_report(content, file_name)
        except ReportFormatError as error:
            run = record("rejected", {}, {"message": str(error)})
            await session.flush()
            return _summary(run)

        issues = parsed.issue_dicts()
        for row in parsed.rows:
            if row.email and not _domain_allowed(row.email, options):
                issues.append(
                    {
                        "line": row.line,
                        "employee_id": row.employee_id,
                        "severity": "warning",
                        "message": f"{row.email} is not an allowed company domain; not invited.",
                    }
                )
                row.email = None
                row.row_hash = row.fingerprint()

        existing = {
            stored.employee_id: stored
            for stored in (
                await session.scalars(
                    select(DirectoryEmployee)
                    .where(DirectoryEmployee.tenant_id == tenant_id)
                    .with_for_update()
                )
            ).all()
        }
        plan = _plan(parsed.rows, existing)
        active_before = sum(1 for record in existing.values() if record.status == "active")
        absent = len(plan.newly_missing) + len(plan.leaving)
        summary: dict[str, object] = {
            "rows": len(parsed.rows),
            "new": len(plan.new),
            "changed": len(plan.changed),
            "returning": len(plan.returning),
            "unchanged": plan.unchanged,
            "missing": len(plan.newly_missing),
            "leaving": len(plan.leaving),
            "issues": len(issues),
            "file_mtime": file_mtime,
        }
        report: dict[str, object] = {
            "issues": issues[:REPORT_LIST_LIMIT],
            "new": _people(plan.new),
            "changed": [
                {"employee_id": row.employee_id, "name": row.display_name, "fields": fields}
                for row, _, fields in plan.changed[:REPORT_LIST_LIMIT]
            ],
            "returning": _people(plan.returning),
            "missing": _people(plan.newly_missing),
            "leaving": _people(plan.leaving),
        }
        drop_ratio = absent / active_before if active_before else 0.0
        if (
            active_before
            and absent >= 5
            and drop_ratio * 100 > options.max_drop_percent
            and not force
        ):
            report["message"] = (
                f"{absent} of {active_before} active employees are missing from this file "
                f"({drop_ratio:.0%}). That looks like a truncated export, so nothing was applied. "
                "Check the file, or apply it with “Apply anyway” if the drop is real."
            )
            run = record("rejected", summary, report)
            await session.flush()
            return _summary(run)
        if not apply:
            run = record("previewed", summary, report)
            await session.flush()
            return _summary(run)

        # Directory rows -------------------------------------------------------------------
        for row in plan.new:
            session.add(
                DirectoryEmployee(
                    tenant_id=tenant_id,
                    employee_id=row.employee_id,
                    first_name=row.first_name,
                    middle_name=row.middle_name,
                    last_name=row.last_name,
                    display_name=row.display_name,
                    email=row.email,
                    location=row.location,
                    department=row.department,
                    sub_department=row.sub_department,
                    manager_employee_id=row.manager_employee_id,
                    hod_employee_id=row.hod_employee_id,
                    row_hash=row.row_hash,
                    status="active",
                    last_seen_at=now,
                )
            )
        email_changes: list[dict[str, str]] = []
        for row, record_, fields in plan.changed + [
            (row, existing[row.employee_id], []) for row in plan.returning
        ]:
            if "email" in fields and record_.user_id is not None:
                email_changes.append(
                    {
                        "employee_id": row.employee_id,
                        "name": row.display_name,
                        "from": record_.email or "",
                        "to": row.email or "",
                    }
                )
            for name in (
                "first_name",
                "middle_name",
                "last_name",
                "email",
                "location",
                "department",
                "sub_department",
                "manager_employee_id",
                "hod_employee_id",
                "row_hash",
            ):
                setattr(record_, name, getattr(row, name))
            record_.display_name = row.display_name
            record_.status = "active"
            record_.missing_runs = 0
        present_ids = {row.employee_id for row in parsed.rows}
        await session.execute(
            update(DirectoryEmployee)
            .where(
                DirectoryEmployee.tenant_id == tenant_id,
                DirectoryEmployee.employee_id.in_(present_ids),
            )
            .values(last_seen_at=now)
        )
        for record_ in plan.newly_missing:
            record_.status = "missing"
            record_.missing_runs += 1
        for record_ in plan.leaving:
            record_.status = "left"
            record_.missing_runs += 1
        await session.flush()

        # Accounts ---------------------------------------------------------------------------
        directory = {
            record_.employee_id: record_
            for record_ in (
                await session.scalars(
                    select(DirectoryEmployee).where(DirectoryEmployee.tenant_id == tenant_id)
                )
            ).all()
        }
        members = await _members_by_email(session, tenant_id)
        for record_ in directory.values():
            if record_.email and record_.user_id is None and record_.email in members:
                membership, user = members[record_.email]
                record_.user_id = user.id
            if record_.user_id is not None:
                for membership, user in members.values():
                    if (
                        user.id == record_.user_id
                        and membership.employee_number != record_.employee_id
                    ):
                        membership.employee_number = record_.employee_id

        approver_ids = {
            value
            for record_ in directory.values()
            if record_.status == "active"
            for value in (record_.manager_employee_id, record_.hod_employee_id)
            if value
        }
        role = await tenant_repository.get_role(session, tenant_id, CONTRIBUTOR)
        invited: list[dict[str, str]] = []
        deferred = 0
        for record_ in sorted(directory.values(), key=lambda item: item.employee_id):
            if record_.status != "active" or not record_.email or role is None:
                continue
            existing_member = members.get(record_.email)
            reinvite = (
                existing_member is not None
                and existing_member[0].status == MembershipStatus.INACTIVE
                and existing_member[0].provisioned_by == "hr_directory"
            )
            wanted = options.invite_new_employees or record_.employee_id in approver_ids
            if not wanted or (existing_member is not None and not reinvite):
                continue
            if len(invited) >= MAX_INVITES_PER_RUN:
                deferred += 1
                continue
            await _queue_invitation(
                session,
                tenant_id=tenant_id,
                tenant_name=tenant.name,
                email=record_.email,
                display_name=record_.display_name,
                inviter=actor,
                role=role,
                settings=settings,
                provisioned_by="hr_directory",
            )
            invited.append(
                {
                    "employee_id": record_.employee_id,
                    "name": record_.display_name,
                    "reason": "approver" if record_.employee_id in approver_ids else "employee",
                }
            )
        if invited:
            members = await _members_by_email(session, tenant_id)
            for record_ in directory.values():
                if record_.email and record_.user_id is None and record_.email in members:
                    membership, user = members[record_.email]
                    record_.user_id = user.id
                    membership.employee_number = record_.employee_id

        deactivated: list[dict[str, str]] = []
        review: list[dict[str, str]] = []
        for record_ in plan.leaving:
            if record_.user_id is None:
                continue
            match = next(((m, u) for m, u in members.values() if u.id == record_.user_id), None)
            if match is None or match[0].status == MembershipStatus.INACTIVE:
                continue
            membership, user = match
            if membership.provisioned_by != "hr_directory":
                review.append(
                    {
                        "employee_id": record_.employee_id,
                        "name": record_.display_name,
                        "reason": "Left per HR, but the account was created by hand. Review it.",
                    }
                )
                continue
            blocked = await _deactivate(session, tenant_id, membership, user, now)
            if blocked:
                review.append(
                    {
                        "employee_id": record_.employee_id,
                        "name": record_.display_name,
                        "reason": f"Left per HR, but {blocked}. Access kept.",
                    }
                )
            else:
                deactivated.append(
                    {"employee_id": record_.employee_id, "name": record_.display_name}
                )
        await session.flush()

        reroutes = await reroute_open_approvals(session, tenant_id, settings, now)

        summary.update(
            {
                "invited": len(invited),
                "invites_deferred": deferred,
                "deactivated": len(deactivated),
                "needs_review": len(review) + len(email_changes),
                "rerouted": len(reroutes),
            }
        )
        report.update(
            {
                "invited": invited[:REPORT_LIST_LIMIT],
                "deactivated": deactivated[:REPORT_LIST_LIMIT],
                "review": review[:REPORT_LIST_LIMIT],
                "email_changes": email_changes[:REPORT_LIST_LIMIT],
                "reroutes": reroutes[:REPORT_LIST_LIMIT],
            }
        )
        if force:
            report["forced"] = True
        run = record("applied", summary, report)
        await session.flush()
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor.user.id if actor else None,
            subject_user_id=None,
            event_type="directory.sync_applied",
            entity_type="directory_run",
            entity_id=run.id,
            entity_reference=file_name[:100],
            summary=(
                f"HR directory updated from {file_name}: {len(plan.new)} new, "
                f"{len(plan.changed)} changed, {len(plan.leaving)} left, "
                f"{len(invited)} invited, {len(deactivated)} deactivated."
            ),
            details={key: value for key, value in summary.items() if key != "file_mtime"},
        )
        return _summary(run)


def inbox_folder(settings: Settings, tenant_slug: str) -> Path:
    return Path(settings.hr_directory_inbox_dir) / tenant_slug


async def process_inbox(
    *,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    actor: SessionIdentity | None,
    settings: Settings,
    session: AsyncSession,
) -> list[DirectoryRunSummary]:
    """Apply every settled file in the workspace's inbox folder, oldest first."""
    folder = inbox_folder(settings, tenant_slug)
    if not folder.is_dir():
        return []
    now = datetime.now(UTC).timestamp()
    files = sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file()
            and path.suffix.casefold() in (".xlsx", ".csv")
            and not path.name.startswith((".", "~$"))
            and now - path.stat().st_mtime >= SETTLE_SECONDS
        ),
        key=lambda path: path.stat().st_mtime,
    )
    results: list[DirectoryRunSummary] = []
    for path in files:
        mtime = path.stat().st_mtime
        result = await run_directory_sync(
            tenant_id=tenant_id,
            content=path.read_bytes(),
            file_name=path.name,
            source="inbox",
            actor=actor,
            settings=settings,
            session=session,
            apply=True,
            file_mtime=mtime,
        )
        destination = folder / (
            "processed" if result.status in ("applied", "duplicate") else "rejected"
        )
        destination.mkdir(exist_ok=True)
        stamped = destination / f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{path.name}"
        shutil.move(str(path), stamped)
        os.chmod(stamped, 0o600)
        results.append(result)
    return results
