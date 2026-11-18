"""Scheduled jobs for every active workspace. Run from cron, e.g. every 15 minutes:

    */15 * * * * cd /srv/transpire/backend && .venv/bin/python scripts/run_scheduled_jobs.py

For each workspace it: fetches the HR report from its SFTP server (at most once per
--fetch-every-hours), applies any file dropped into its local inbox folder, and sends
overdue approval reminders. Every step is idempotent, so overlapping or repeated runs
are harmless; a failure in one workspace never stops the others.
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.database import session_factory
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.directory.models import DirectorySftpSource
from app.domains.directory.sftp_controllers import fetch_and_apply
from app.domains.directory.sync import process_inbox
from app.domains.ideas.approval_reminders import send_overdue_reminders


async def _sftp_due(tenant_id, every: timedelta) -> bool:
    async with session_factory() as session, session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        source = await session.scalar(
            select(DirectorySftpSource).where(DirectorySftpSource.tenant_id == tenant_id)
        )
        if source is None or not source.enabled or not source.trusted_host_key:
            return False
        return source.last_run_at is None or source.last_run_at <= datetime.now(UTC) - every


async def run(only: str | None, fetch_every: timedelta, skip_sftp: bool) -> int:
    settings = get_settings()
    async with session_factory() as session:
        tenants = (
            (await session.execute(text("SELECT * FROM list_platform_tenants()"))).mappings().all()
        )
    failures = 0
    for tenant in tenants:
        slug, tenant_id = tenant["slug"], tenant["tenant_id"]
        if tenant["status"] != "active" or (only and slug != only):
            continue
        try:
            if not skip_sftp and await _sftp_due(tenant_id, fetch_every):
                async with session_factory() as session:
                    result = await fetch_and_apply(
                        tenant_id=tenant_id,
                        tenant_slug=slug,
                        actor=None,
                        settings=settings,
                        session=session,
                    )
                print(f"{slug}: SFTP {'ok' if result.ok else 'FAILED'}: {result.message}")
                failures += 0 if result.ok else 1
            async with session_factory() as session:
                for run_ in await process_inbox(
                    tenant_id=tenant_id,
                    tenant_slug=slug,
                    actor=None,
                    settings=settings,
                    session=session,
                ):
                    print(f"{slug}: inbox {run_.file_name} -> {run_.status}")
            async with session_factory() as session:
                sent = await send_overdue_reminders(tenant_id, settings, session)
            if sent.reminded or sent.escalated:
                print(f"{slug}: {sent.reminded} reminder(s), {sent.escalated} escalation(s)")
        except Exception as error:  # noqa: BLE001 - one workspace must never block the rest
            failures += 1
            print(f"{slug}: FAILED {type(error).__name__}: {error}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tenant", help="Only this workspace shortname")
    parser.add_argument("--fetch-every-hours", type=float, default=24.0)
    parser.add_argument("--skip-sftp", action="store_true")
    args = parser.parse_args()
    failures = asyncio.run(
        run(args.tenant, timedelta(hours=args.fetch_every_hours), args.skip_sftp)
    )
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
