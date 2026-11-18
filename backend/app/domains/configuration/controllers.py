import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.audit.controllers import record_audit_event
from app.domains.configuration.models import (
    ApproverGroup,
    ConfigurationItem,
    WorkflowDefinition,
    WorkflowVersion,
    WorkflowVersionStatus,
)
from app.domains.configuration.repositories import SQLAlchemyConfigurationRepository
from app.domains.configuration.schemas import (
    ApproverGroupCommand,
    ApproverGroupMember,
    ApproverGroupSummary,
    ConfigurationItemCreate,
    ConfigurationItemSummary,
    ConfigurationItemUpdate,
    PreviewApprover,
    PreviewStep,
    WorkflowAssigneeSummary,
    WorkflowPreviewCommand,
    WorkflowPreviewResult,
    WorkflowStage,
    WorkflowSummary,
    WorkflowVersionCreate,
    WorkflowVersionSummary,
)
from app.domains.configuration.urs_templates import URS_TEMPLATE_CATALOG


class ConfigurationConflictError(Exception):
    pass


class ConfigurationNotFoundError(Exception):
    pass


repository = SQLAlchemyConfigurationRepository()
PARENT_KIND = {"subcategory": "category"}
DEMO_STAGES = [
    {
        "key": "demo_approval",
        "name": "Demo Approval",
        "approver_role": "tenant_admin",
        "source": "group",
        "group_id": None,
        "mode": "any",
        "on_unresolved": "fallback_admin",
        "skip_if_same_as_previous": False,
        "sla_hours": 48,
        "required": True,
    }
]


def create_default_workflow(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    workflow_id = uuid.uuid4()
    workflow = WorkflowDefinition(
        id=workflow_id,
        tenant_id=tenant_id,
        key="idea_approval",
        name="Idea Approval",
        description="Default approval contract for submitted ideas.",
    )
    session.add(workflow)
    session.add(
        WorkflowVersion(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            version=1,
            status=WorkflowVersionStatus.PUBLISHED,
            stages=DEMO_STAGES,
            published_at=datetime.now(UTC),
        )
    )


def _code(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def create_default_master_data(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Attach the immutable URS starter catalogue to a newly created tenant."""
    for category_index, category in enumerate(URS_TEMPLATE_CATALOG["categories"]):
        assert isinstance(category, dict)
        category_id = uuid.uuid4()
        category_code = _code(str(category["name"]))
        session.add(
            ConfigurationItem(
                id=category_id,
                tenant_id=tenant_id,
                kind="category",
                code=category_code,
                name=str(category["name"]),
                sort_order=category_index,
                guidance={"applies": str(category.get("applies", "Both")), "source": "URS"},
            )
        )
        for subcategory_index, subcategory in enumerate(category["subs"]):
            assert isinstance(subcategory, dict)
            session.add(
                ConfigurationItem(
                    tenant_id=tenant_id,
                    kind="subcategory",
                    code=f"{category_code}_{_code(str(subcategory['name']))}",
                    name=str(subcategory["name"]),
                    parent_id=category_id,
                    sort_order=subcategory_index,
                    guidance={
                        "title_template": str(subcategory["titleTemplate"]),
                        "problem": str(subcategory["problem"]),
                        "business_case": str(subcategory["solution"]),
                        "kpi": str(subcategory["kpi"]),
                        "area": str(subcategory["area"]),
                        "source": "URS",
                    },
                )
            )
    for area_index, area in enumerate(URS_TEMPLATE_CATALOG["processAreas"]):
        session.add(
            ConfigurationItem(
                tenant_id=tenant_id,
                kind="process_area",
                code=_code(str(area)),
                name=str(area),
                sort_order=area_index,
                guidance={"source": "URS"},
            )
        )


def _item_summary(
    item: ConfigurationItem, site_ids: list[uuid.UUID] | None = None
) -> ConfigurationItemSummary:
    return ConfigurationItemSummary(
        id=item.id,
        kind=item.kind,
        code=item.code,
        name=item.name,
        parent_id=item.parent_id,
        site_ids=site_ids or [],
        applies_to_all_sites=item.applies_to_all_sites,
        is_active=item.is_active,
        sort_order=item.sort_order,
        guidance=item.guidance,
    )


async def list_items(
    tenant_id: uuid.UUID, kind: str, session: AsyncSession
) -> list[ConfigurationItemSummary]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        items = await repository.list_items(session, tenant_id, kind)
        site_ids = await repository.department_site_ids(
            session, tenant_id, [item.id for item in items if item.kind == "department"]
        )
        return [_item_summary(item, site_ids.get(item.id)) for item in items]


async def _validated_department_sites(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    site_ids: list[uuid.UUID],
    applies_to_all_sites: bool,
) -> list[uuid.UUID]:
    unique_site_ids = list(dict.fromkeys(site_ids))
    if applies_to_all_sites:
        return []
    if not unique_site_ids:
        raise ConfigurationConflictError("Select at least one site or choose All sites.")
    for site_id in unique_site_ids:
        site = await repository.get_item(session, tenant_id, site_id)
        if site is None or site.kind != "site" or not site.is_active:
            raise ConfigurationConflictError("Select active sites only.")
    return unique_site_ids


async def create_item(
    tenant_id: uuid.UUID, kind: str, command: ConfigurationItemCreate, session: AsyncSession
) -> ConfigurationItemSummary:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        if kind == "department":
            legacy_site_ids = (
                [command.parent_id] if command.parent_id and not command.site_ids else []
            )
            site_ids = await _validated_department_sites(
                session,
                tenant_id,
                command.site_ids or legacy_site_ids,
                command.applies_to_all_sites,
            )
        elif command.site_ids or command.applies_to_all_sites:
            raise ConfigurationConflictError("Site scope is only available for departments.")
        else:
            site_ids = []
        expected_parent = PARENT_KIND.get(kind)
        if expected_parent:
            if command.parent_id is None:
                raise ConfigurationConflictError(
                    f"A {expected_parent.replace('_', ' ')} is required."
                )
            parent = await repository.get_item(session, tenant_id, command.parent_id)
            if parent is None or parent.kind != expected_parent or not parent.is_active:
                raise ConfigurationConflictError(
                    f"Select an active {expected_parent.replace('_', ' ')}."
                )
        elif command.parent_id is not None and kind != "department":
            raise ConfigurationConflictError("This configuration type cannot have a parent.")
        item = ConfigurationItem(
            tenant_id=tenant_id,
            kind=kind,
            code=command.code,
            name=command.name,
            parent_id=command.parent_id if kind != "department" else None,
            applies_to_all_sites=command.applies_to_all_sites if kind == "department" else False,
            sort_order=command.sort_order,
            is_active=True,
            guidance=command.guidance,
        )
        session.add(item)
        await session.flush()
        if kind == "department":
            await repository.replace_department_sites(session, tenant_id, item.id, site_ids)
        return _item_summary(item, site_ids)


async def update_item(
    tenant_id: uuid.UUID,
    kind: str,
    item_id: uuid.UUID,
    command: ConfigurationItemUpdate,
    session: AsyncSession,
) -> ConfigurationItemSummary:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        item = await repository.get_item(session, tenant_id, item_id)
        if item is None or item.kind != kind:
            raise ConfigurationNotFoundError
        if command.is_active is False and await repository.active_children(
            session, tenant_id, item_id
        ):
            raise ConfigurationConflictError("Deactivate dependent records first.")
        values = command.model_dump(exclude_unset=True)
        site_ids = values.pop("site_ids", None)
        applies_to_all_sites = values.pop("applies_to_all_sites", None)
        if kind == "department" and (site_ids is not None or applies_to_all_sites is not None):
            current_site_ids = (
                await repository.department_site_ids(session, tenant_id, [item.id])
            ).get(item.id, [])
            next_all_sites = (
                applies_to_all_sites
                if applies_to_all_sites is not None
                else item.applies_to_all_sites
            )
            next_site_ids = site_ids if site_ids is not None else current_site_ids
            validated_site_ids = await _validated_department_sites(
                session, tenant_id, next_site_ids, next_all_sites
            )
            item.applies_to_all_sites = next_all_sites
            await repository.replace_department_sites(
                session, tenant_id, item.id, validated_site_ids
            )
        elif kind != "department" and (site_ids is not None or applies_to_all_sites is not None):
            raise ConfigurationConflictError("Site scope is only available for departments.")
        for field, value in values.items():
            setattr(item, field, value)
        await session.flush()
        resolved_site_ids = (
            (await repository.department_site_ids(session, tenant_id, [item.id])).get(item.id, [])
            if kind == "department"
            else []
        )
        return _item_summary(item, resolved_site_ids)


def _workflow_summary(
    definition: WorkflowDefinition, versions: list[WorkflowVersion]
) -> WorkflowSummary:
    return WorkflowSummary(
        id=definition.id,
        key=definition.key,
        name=definition.name,
        description=definition.description,
        is_active=definition.is_active,
        versions=[
            WorkflowVersionSummary(
                id=version.id,
                version=version.version,
                status=version.status.value,
                stages=[WorkflowStage.model_validate(stage) for stage in version.stages],
                published_at=version.published_at,
                created_at=version.created_at,
            )
            for version in versions
        ],
    )


async def list_workflows(tenant_id: uuid.UUID, session: AsyncSession) -> list[WorkflowSummary]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        return [
            _workflow_summary(definition, versions)
            for definition, versions in await repository.list_workflows(session, tenant_id)
        ]


async def list_workflow_assignees(
    tenant_id: uuid.UUID, session: AsyncSession, query: str | None = None, limit: int = 20
) -> list[WorkflowAssigneeSummary]:
    """People who can approve. With ``query``, a name or email search capped at ``limit``."""
    term = None if query is None else query.strip()
    if term is not None and len(term) < 2:
        return []
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        records = await repository.list_workflow_assignees(
            session, tenant_id, search=term, limit=limit if term is not None else None
        )
        return [
            WorkflowAssigneeSummary(
                membership_id=record.membership.id,
                display_name=record.user.display_name,
                email=record.user.email,
                status=record.status,
            )
            for record in records
        ]


async def _groups_by_id(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, ApproverGroup]:
    return {
        str(group.id): group
        for group in (
            await session.scalars(select(ApproverGroup).where(ApproverGroup.tenant_id == tenant_id))
        ).all()
    }


async def _resolve_workflow_stages(
    tenant_id: uuid.UUID,
    command: WorkflowVersionCreate,
    session: AsyncSession,
) -> list[WorkflowStage]:
    assignees = {
        record.membership.id: record
        for record in await repository.list_workflow_assignees(session, tenant_id)
    }
    groups = await _groups_by_id(session, tenant_id)
    resolved: list[WorkflowStage] = []
    for stage in command.stages:
        extra: dict[str, object] = {}
        if stage.source == "person":
            assignee = assignees.get(stage.assignee_membership_id)
            if assignee is None:
                raise ConfigurationConflictError(
                    f"Select an active member or pending invitee for {stage.name}."
                )
            extra = {
                "assignee_name": assignee.user.display_name,
                "assignee_email": assignee.user.email,
                "assignee_status": assignee.status,
            }
        if stage.source == "group":
            group = groups.get(str(stage.group_id))
            if group is None or not group.is_active or group.purpose != "approval":
                raise ConfigurationConflictError(f"{stage.name}: choose an active approval group.")
            extra["group_name"] = group.name
        if stage.on_unresolved == "fallback_group":
            fallback = groups.get(str(stage.fallback_group_id))
            if fallback is None or not fallback.is_active or fallback.purpose != "approval":
                raise ConfigurationConflictError(
                    f"{stage.name}: choose an active approval group as the fallback."
                )
            extra["fallback_group_name"] = fallback.name
        if stage.notify_kind == "group":
            notify = groups.get(str(stage.notify_group_id))
            if notify is None or not notify.is_active:
                raise ConfigurationConflictError(f"{stage.name}: choose an active group to notify.")
            extra["notify_group_name"] = notify.name
        resolved.append(WorkflowStage(**stage.model_dump(), approver_role=stage.source, **extra))
    return resolved


async def create_workflow_version(
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    command: WorkflowVersionCreate,
    session: AsyncSession,
) -> WorkflowVersionSummary:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        workflow = await repository.get_workflow(session, tenant_id, workflow_id)
        if workflow is None:
            raise ConfigurationNotFoundError
        stages = await _resolve_workflow_stages(tenant_id, command, session)
        version = WorkflowVersion(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            version=await repository.next_version(session, workflow_id),
            status=WorkflowVersionStatus.DRAFT,
            stages=[stage.model_dump(mode="json") for stage in stages],
        )
        session.add(version)
        await session.flush()
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            subject_user_id=actor_user_id,
            event_type="workflow.version_created",
            entity_type="workflow_version",
            entity_id=version.id,
            entity_reference=f"{workflow.name} v{version.version}",
            summary=f"Created draft version {version.version} of {workflow.name}.",
            details={"workflow_id": str(workflow_id), "stage_count": len(stages)},
        )
        return WorkflowVersionSummary(
            id=version.id,
            version=version.version,
            status=version.status.value,
            stages=stages,
            published_at=None,
            created_at=version.created_at,
        )


async def publish_workflow_version(
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    version_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        version = await repository.get_version(session, tenant_id, workflow_id, version_id)
        if version is None:
            raise ConfigurationNotFoundError
        if version.status != WorkflowVersionStatus.DRAFT:
            raise ConfigurationConflictError("Only a draft workflow version can be published.")
        assignable_ids = {
            record.membership.id
            for record in await repository.list_workflow_assignees(session, tenant_id)
        }
        groups = await _groups_by_id(session, tenant_id)
        for stage in version.stages:
            name = stage.get("name", "A stage")
            source = stage.get("source") or "person"
            if source == "person":
                assignee_id = stage.get("assignee_membership_id")
                if not assignee_id or uuid.UUID(str(assignee_id)) not in assignable_ids:
                    raise ConfigurationConflictError(
                        f"{name}: the assigned person must be an active member or pending invitee."
                    )
            if source == "group":
                group = groups.get(str(stage.get("group_id")))
                members = {str(value) for value in group.member_membership_ids} if group else set()
                if (
                    not group
                    or not group.is_active
                    or group.purpose != "approval"
                    or not members & {str(value) for value in assignable_ids}
                ):
                    raise ConfigurationConflictError(
                        f"{name}: the approver group needs at least one person who can approve."
                    )
            if stage.get("on_unresolved") == "fallback_group":
                fallback = groups.get(str(stage.get("fallback_group_id")))
                if not fallback or not fallback.is_active:
                    raise ConfigurationConflictError(
                        f"{name}: the fallback approver group is missing or inactive."
                    )
        await session.execute(
            update(WorkflowVersion)
            .where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.workflow_id == workflow_id,
                WorkflowVersion.status == WorkflowVersionStatus.PUBLISHED,
            )
            .values(status=WorkflowVersionStatus.RETIRED)
        )
        version.status = WorkflowVersionStatus.PUBLISHED
        version.published_at = datetime.now(UTC)
        workflow = await repository.get_workflow(session, tenant_id, workflow_id)
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            subject_user_id=actor_user_id,
            event_type="workflow.version_published",
            entity_type="workflow_version",
            entity_id=version.id,
            entity_reference=f"{workflow.name if workflow else 'Approval workflow'} v{version.version}",
            summary=f"Published approval workflow version {version.version}.",
            details={"workflow_id": str(workflow_id), "stage_count": len(version.stages)},
        )


async def _group_summary(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    group: ApproverGroup,
    assignees: dict[uuid.UUID, object],
    published_group_ids: set[str],
) -> ApproverGroupSummary:
    members: list[ApproverGroupMember] = []
    for raw_id in group.member_membership_ids:
        record = assignees.get(uuid.UUID(str(raw_id)))
        if record is None:
            members.append(
                ApproverGroupMember(
                    membership_id=uuid.UUID(str(raw_id)),
                    display_name="No longer able to approve",
                    email="",
                    status="unavailable",
                )
            )
            continue
        members.append(
            ApproverGroupMember(
                membership_id=record.membership.id,
                display_name=record.user.display_name,
                email=record.user.email,
                status=record.status,
            )
        )
    return ApproverGroupSummary(
        id=group.id,
        name=group.name,
        purpose=group.purpose,  # type: ignore[arg-type]
        description=group.description,
        is_active=group.is_active,
        members=members,
        used_by_published_workflow=str(group.id) in published_group_ids,
    )


async def _published_group_ids(session: AsyncSession, tenant_id: uuid.UUID) -> set[str]:
    ids: set[str] = set()
    for stages in (
        await session.scalars(
            select(WorkflowVersion.stages).where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.status == WorkflowVersionStatus.PUBLISHED,
            )
        )
    ).all():
        for stage in stages:
            for key in ("group_id", "fallback_group_id", "notify_group_id"):
                if stage.get(key):
                    ids.add(str(stage[key]))
    return ids


async def _published_approver_group_ids(session: AsyncSession, tenant_id: uuid.UUID) -> set[str]:
    ids: set[str] = set()
    for stages in (
        await session.scalars(
            select(WorkflowVersion.stages).where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.status == WorkflowVersionStatus.PUBLISHED,
            )
        )
    ).all():
        for stage in stages:
            for key in ("group_id", "fallback_group_id"):
                if stage.get(key):
                    ids.add(str(stage[key]))
    return ids


async def list_approver_groups(
    tenant_id: uuid.UUID, session: AsyncSession
) -> list[ApproverGroupSummary]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        assignees = {
            record.membership.id: record
            for record in await repository.list_workflow_assignees(session, tenant_id)
        }
        published = await _published_group_ids(session, tenant_id)
        groups = (
            await session.scalars(
                select(ApproverGroup)
                .where(ApproverGroup.tenant_id == tenant_id)
                .order_by(ApproverGroup.name)
            )
        ).all()
        return [
            await _group_summary(session, tenant_id, group, assignees, published)
            for group in groups
        ]


async def save_approver_group(
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    group_id: uuid.UUID | None,
    command: ApproverGroupCommand,
    session: AsyncSession,
) -> ApproverGroupSummary:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        assignees = {
            record.membership.id: record
            for record in await repository.list_workflow_assignees(session, tenant_id)
        }
        unavailable = [
            member for member in command.member_membership_ids if member not in assignees
        ]
        if unavailable:
            raise ConfigurationConflictError(
                "Approver groups can include only active or invited people who can approve "
                "(not Viewers)."
            )
        published = await _published_group_ids(session, tenant_id)
        if group_id is None:
            group = ApproverGroup(tenant_id=tenant_id, round_robin_cursor=0)
            session.add(group)
            event = "approver_group.created"
        else:
            group = await session.scalar(
                select(ApproverGroup)
                .where(ApproverGroup.tenant_id == tenant_id, ApproverGroup.id == group_id)
                .with_for_update()
            )
            if group is None:
                raise ConfigurationNotFoundError
            if not command.is_active and str(group.id) in published:
                raise ConfigurationConflictError(
                    "This group is used by the published approval workflow. "
                    "Publish a version without it before deactivating it."
                )
            if (
                group.purpose == "approval"
                and command.purpose == "notification"
                and str(group.id) in await _published_approver_group_ids(session, tenant_id)
            ):
                raise ConfigurationConflictError(
                    "This group approves a step in the published workflow, so it cannot become "
                    "notification-only. Publish a version without it first."
                )
            event = "approver_group.updated"
        before = [str(value) for value in group.member_membership_ids or []]
        group.name = command.name.strip()
        group.purpose = command.purpose
        group.description = command.description.strip()
        group.member_membership_ids = [str(member) for member in command.member_membership_ids]
        group.is_active = command.is_active
        await session.flush()
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            subject_user_id=actor_user_id,
            event_type=event,
            entity_type="approver_group",
            entity_id=group.id,
            entity_reference=group.name,
            summary=f"{'Created' if group_id is None else 'Updated'} approver group {group.name}.",
            details={"members_before": before, "members_after": group.member_membership_ids},
        )
        return await _group_summary(session, tenant_id, group, assignees, published)


async def preview_workflow(
    tenant_id: uuid.UUID, command: WorkflowPreviewCommand, session: AsyncSession
) -> WorkflowPreviewResult:
    """Show who would approve each step for one employee, without changing anything."""
    from app.domains.directory.models import DirectoryEmployee
    from app.domains.ideas.approval_routing import MODE_LABELS, resolve_step

    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        subject = await session.scalar(
            select(DirectoryEmployee).where(
                DirectoryEmployee.tenant_id == tenant_id,
                DirectoryEmployee.employee_id == command.employee_id.strip(),
            )
        )
        if subject is None:
            raise ConfigurationNotFoundError
        submitter_id = subject.user_id or uuid.uuid4()
        steps: list[PreviewStep] = []
        previous: set[uuid.UUID] = set()
        for stage in command.stages:
            payload = stage.model_dump(mode="json")
            resolved = await resolve_step(
                session,
                tenant_id,
                payload,
                submitter_id,
                previous,
                activate=False,
                subject=subject,
                subject_loaded=True,
            )
            if not resolved.skipped:
                previous = {approver.user_id for approver in resolved.approvers}
            steps.append(
                PreviewStep(
                    key=stage.key,
                    name=stage.name,
                    outcome="skipped" if resolved.skipped else "assigned",
                    mode=MODE_LABELS.get(stage.mode, stage.mode)
                    if stage.source == "group"
                    else "Single approver",
                    approvers=[
                        PreviewApprover(display_name=approver.name, email=approver.email)
                        for approver in resolved.approvers
                    ],
                    note=resolved.note,
                )
            )
        return WorkflowPreviewResult(
            employee_name=subject.display_name, employee_email=subject.email, steps=steps
        )
