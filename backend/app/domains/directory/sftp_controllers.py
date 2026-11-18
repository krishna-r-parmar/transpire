import hashlib
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.secrets import encrypt_secret
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.audit.controllers import record_audit_event
from app.domains.directory.models import DirectoryRun, DirectorySftpSource
from app.domains.directory.schemas import (
    DirectoryRunSummary,
    SftpActionResult,
    SftpSourceCommand,
    SftpSourceView,
)
from app.domains.directory.sftp import (
    SftpError,
    archive_copy,
    fetch_latest,
    fingerprint,
    scan_host_key,
    test_connection,
)
from app.domains.directory.sync import inbox_folder, run_directory_sync
from app.domains.identity.schemas import SessionIdentity

SOURCE_FIELDS = (
    "enabled",
    "host",
    "port",
    "username",
    "auth_method",
    "encrypted_secret",
    "remote_path",
    "trusted_host_key",
    "presented_host_key",
)


class SftpNotConfiguredError(Exception):
    pass


def _view(source: DirectorySftpSource | None) -> SftpSourceView:
    if source is None:
        return SftpSourceView(
            enabled=False,
            host="",
            port=22,
            username="",
            auth_method="password",
            has_secret=False,
            remote_path="",
            trusted_fingerprint=None,
            presented_fingerprint=None,
            key_awaiting_trust=False,
            last_run_at=None,
            last_status=None,
            last_message=None,
        )
    trusted = fingerprint(source.trusted_host_key)
    presented = fingerprint(source.presented_host_key)
    return SftpSourceView(
        enabled=source.enabled,
        host=source.host,
        port=source.port,
        username=source.username,
        auth_method=source.auth_method,
        has_secret=bool(source.encrypted_secret),
        remote_path=source.remote_path,
        trusted_fingerprint=trusted,
        presented_fingerprint=presented,
        key_awaiting_trust=bool(presented and presented != trusted),
        last_run_at=source.last_run_at,
        last_status=source.last_status,
        last_message=source.last_message,
    )


async def _source(
    session: AsyncSession, tenant_id: uuid.UUID, *, lock: bool = False
) -> DirectorySftpSource | None:
    statement = select(DirectorySftpSource).where(DirectorySftpSource.tenant_id == tenant_id)
    return await session.scalar(statement.with_for_update() if lock else statement)


async def _snapshot(session: AsyncSession, tenant_id: uuid.UUID) -> SimpleNamespace:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        source = await _source(session, tenant_id)
        if source is None or not source.host:
            raise SftpNotConfiguredError
        return SimpleNamespace(**{name: getattr(source, name) for name in SOURCE_FIELDS})


async def _record_outcome(
    session: AsyncSession, tenant_id: uuid.UUID, status: str, message: str
) -> SftpSourceView:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        source = await _source(session, tenant_id, lock=True)
        assert source is not None
        source.last_run_at = datetime.now(UTC)
        source.last_status = status
        source.last_message = message[:1000]
        return _view(source)


async def get_sftp_source(tenant_id: uuid.UUID, session: AsyncSession) -> SftpSourceView:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        return _view(await _source(session, tenant_id))


async def save_sftp_source(
    tenant_id: uuid.UUID,
    actor: SessionIdentity,
    command: SftpSourceCommand,
    settings: Settings,
    session: AsyncSession,
) -> SftpSourceView:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        source = await _source(session, tenant_id, lock=True)
        if source is None:
            source = DirectorySftpSource(tenant_id=tenant_id)
            session.add(source)
        moved = (source.host, source.port) != (command.host.strip(), command.port)
        source.enabled = command.enabled
        source.host = command.host.strip()
        source.port = command.port
        source.username = command.username.strip()
        source.remote_path = command.remote_path.strip()
        if command.auth_method != source.auth_method and not command.secret:
            source.encrypted_secret = None  # a password cannot be reused as a key
        source.auth_method = command.auth_method
        if command.secret:
            source.encrypted_secret = encrypt_secret(command.secret.strip(), settings)
        if moved:
            # A different server must be checked and trusted again.
            source.trusted_host_key = None
            source.presented_host_key = None
        if source.enabled and not source.trusted_host_key:
            source.enabled = False
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor.user.id,
            subject_user_id=actor.user.id,
            event_type="directory.sftp_updated",
            entity_type="directory_sftp_source",
            entity_id=None,
            entity_reference=f"{source.host}:{source.port}",
            summary=f"Updated the HR SFTP connection to {source.host}:{source.port}.",
            details={
                "host": source.host,
                "port": source.port,
                "username": source.username,
                "remote_path": source.remote_path,
                "secret_changed": bool(command.secret),
                "enabled": source.enabled,
            },
        )
        await session.flush()
        return _view(source)


async def check_server_key(
    tenant_id: uuid.UUID, settings: Settings, session: AsyncSession
) -> SftpActionResult:
    snapshot = await _snapshot(session, tenant_id)
    try:
        key, presented = await scan_host_key(snapshot, settings)  # type: ignore[arg-type]
    except SftpError as error:
        view = await _record_outcome(session, tenant_id, "failed", str(error))
        return SftpActionResult(ok=False, message=str(error), source=view)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        source = await _source(session, tenant_id, lock=True)
        assert source is not None
        source.presented_host_key = key
        view = _view(source)
    if view.trusted_fingerprint == presented:
        return SftpActionResult(
            ok=True, message="The server's key matches the trusted key.", source=view
        )
    return SftpActionResult(
        ok=True,
        message=(
            f"The server presented {presented}. Confirm this fingerprint with the customer's IT "
            "team, then trust it."
        ),
        source=view,
    )


async def trust_server_key(
    tenant_id: uuid.UUID, actor: SessionIdentity, fingerprint_value: str, session: AsyncSession
) -> SftpSourceView:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        source = await _source(session, tenant_id, lock=True)
        if source is None or not source.presented_host_key:
            raise SftpNotConfiguredError
        if fingerprint(source.presented_host_key) != fingerprint_value.strip():
            raise SftpNotConfiguredError
        previous = fingerprint(source.trusted_host_key)
        source.trusted_host_key = source.presented_host_key
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor.user.id,
            subject_user_id=actor.user.id,
            event_type="directory.sftp_key_trusted",
            entity_type="directory_sftp_source",
            entity_id=source.id,
            entity_reference=f"{source.host}:{source.port}",
            summary=f"Trusted the SFTP server key {fingerprint_value.strip()}.",
            details={"previous": previous, "trusted": fingerprint_value.strip()},
        )
        return _view(source)


async def test_sftp_source(
    tenant_id: uuid.UUID, settings: Settings, session: AsyncSession
) -> SftpActionResult:
    snapshot = await _snapshot(session, tenant_id)
    try:
        message = await test_connection(snapshot, settings)  # type: ignore[arg-type]
        view = await _record_outcome(session, tenant_id, "tested", message)
        return SftpActionResult(ok=True, message=message, source=view)
    except SftpError as error:
        view = await _record_outcome(session, tenant_id, "failed", str(error))
        return SftpActionResult(ok=False, message=str(error), source=view)


async def fetch_and_apply(
    *,
    tenant_id: uuid.UUID,
    tenant_slug: str,
    actor: SessionIdentity | None,
    settings: Settings,
    session: AsyncSession,
) -> SftpActionResult:
    """Download the newest report and run it through the normal, idempotent sync."""
    snapshot = await _snapshot(session, tenant_id)
    try:
        fetched = await fetch_latest(snapshot, settings)  # type: ignore[arg-type]
    except SftpError as error:
        async with session.begin():
            await apply_tenant_to_transaction(session, tenant_id)
            session.add(
                DirectoryRun(
                    tenant_id=tenant_id,
                    file_name=f"{snapshot.host}:{snapshot.remote_path}"[:255],
                    file_sha256=hashlib.sha256(b"").hexdigest(),
                    source="sftp",
                    status="failed",
                    summary={},
                    report={"message": str(error)},
                    actor_user_id=actor.user.id if actor else None,
                )
            )
        view = await _record_outcome(session, tenant_id, "failed", str(error))
        return SftpActionResult(ok=False, message=str(error), source=view)
    run: DirectoryRunSummary = await run_directory_sync(
        tenant_id=tenant_id,
        content=fetched.content,
        file_name=fetched.name,
        source="sftp",
        actor=actor,
        settings=settings,
        session=session,
        apply=True,
        file_mtime=fetched.modified,
    )
    archive_copy(inbox_folder(settings, tenant_slug), fetched, run.status)
    message = {
        "applied": f"Fetched and applied {fetched.name}.",
        "duplicate": f"{fetched.name} has not changed since it was last applied.",
    }.get(
        run.status,
        f"Fetched {fetched.name}, but it was {run.status}: {run.report.get('message', '')}",
    )
    view = await _record_outcome(
        session, tenant_id, "ok" if run.status in ("applied", "duplicate") else run.status, message
    )
    return SftpActionResult(
        ok=run.status in ("applied", "duplicate"), message=message, source=view, run=run
    )
