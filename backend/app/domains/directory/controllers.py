import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.audit.controllers import record_audit_event
from app.domains.directory.models import DirectoryEmployee, DirectoryRun
from app.domains.directory.schemas import (
    DirectoryEmployeeSummary,
    DirectoryOverview,
    DirectoryRunSummary,
    DirectorySettings,
)
from app.domains.directory.sync import inbox_folder, read_settings
from app.domains.tenants.models import Tenant


async def get_overview(
    tenant_id: uuid.UUID, tenant_slug: str, settings: Settings, session: AsyncSession
) -> DirectoryOverview:
    folder = inbox_folder(settings, tenant_slug)
    waiting = (
        sorted(
            path.name
            for path in folder.iterdir()
            if path.is_file() and path.suffix.casefold() in (".xlsx", ".csv")
        )
        if folder.is_dir()
        else []
    )
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        tenant = await session.get(Tenant, tenant_id)
        assert tenant is not None
        counts = dict(
            (
                await session.execute(
                    select(DirectoryEmployee.status, func.count())
                    .where(DirectoryEmployee.tenant_id == tenant_id)
                    .group_by(DirectoryEmployee.status)
                )
            ).all()
        )
        with_account = await session.scalar(
            select(func.count()).where(
                DirectoryEmployee.tenant_id == tenant_id,
                DirectoryEmployee.status != "left",
                DirectoryEmployee.user_id.is_not(None),
            )
        )
        last_applied = await session.scalar(
            select(func.max(DirectoryRun.created_at)).where(
                DirectoryRun.tenant_id == tenant_id, DirectoryRun.status == "applied"
            )
        )
        return DirectoryOverview(
            settings=read_settings(tenant),
            inbox_folder=f"{folder.parent.name}/{folder.name}",
            inbox_waiting=waiting,
            employees_active=int(counts.get("active", 0)),
            employees_missing=int(counts.get("missing", 0)),
            employees_left=int(counts.get("left", 0)),
            employees_with_account=int(with_account or 0),
            last_applied_at=last_applied,
        )


async def update_settings(
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    command: DirectorySettings,
    session: AsyncSession,
) -> DirectorySettings:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        tenant = await session.get(Tenant, tenant_id, with_for_update=True)
        assert tenant is not None
        before = read_settings(tenant)
        tenant.settings = {**(tenant.settings or {}), "hr_directory": command.model_dump()}
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            subject_user_id=actor_user_id,
            event_type="directory.settings_updated",
            entity_type="tenant",
            entity_id=tenant_id,
            entity_reference="HR directory",
            summary="Updated HR directory settings.",
            details={"before": before.model_dump(), "after": command.model_dump()},
        )
        return command


async def list_runs(tenant_id: uuid.UUID, session: AsyncSession) -> list[DirectoryRunSummary]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        runs = (
            await session.scalars(
                select(DirectoryRun)
                .where(DirectoryRun.tenant_id == tenant_id)
                .order_by(DirectoryRun.created_at.desc())
                .limit(30)
            )
        ).all()
        return [
            DirectoryRunSummary(
                id=run.id,
                file_name=run.file_name,
                source=run.source,
                status=run.status,
                created_at=run.created_at,
                summary=run.summary,
                report=run.report,
            )
            for run in runs
        ]


async def search_employees(
    tenant_id: uuid.UUID, query: str, session: AsyncSession, limit: int = 50
) -> list[DirectoryEmployeeSummary]:
    manager = aliased(DirectoryEmployee)
    hod = aliased(DirectoryEmployee)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        statement = (
            select(DirectoryEmployee, manager.display_name, hod.display_name)
            .outerjoin(
                manager,
                (manager.tenant_id == tenant_id)
                & (manager.employee_id == DirectoryEmployee.manager_employee_id),
            )
            .outerjoin(
                hod,
                (hod.tenant_id == tenant_id)
                & (hod.employee_id == DirectoryEmployee.hod_employee_id),
            )
            .where(DirectoryEmployee.tenant_id == tenant_id)
            .order_by(DirectoryEmployee.status, DirectoryEmployee.display_name)
            .limit(limit)
        )
        term = query.strip()
        if term:
            pattern = f"%{term}%"
            statement = statement.where(
                DirectoryEmployee.display_name.ilike(pattern)
                | DirectoryEmployee.employee_id.ilike(pattern)
                | DirectoryEmployee.email.ilike(pattern)
                | DirectoryEmployee.department.ilike(pattern)
            )
        return [
            DirectoryEmployeeSummary(
                employee_id=employee.employee_id,
                display_name=employee.display_name,
                email=employee.email,
                location=employee.location,
                department=employee.department,
                sub_department=employee.sub_department,
                manager_employee_id=employee.manager_employee_id,
                manager_name=manager_name,
                hod_employee_id=employee.hod_employee_id,
                hod_name=hod_name,
                status=employee.status,
                has_account=employee.user_id is not None,
            )
            for employee, manager_name, hod_name in (await session.execute(statement)).all()
        ]
