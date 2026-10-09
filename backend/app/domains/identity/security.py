import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None = None


def authentication_key(action: str, identifier: str, ip_address: str | None) -> str:
    normalized = f"{action}:{identifier.casefold()}:{ip_address or 'unknown'}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def consume_rate_limit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: str,
    key_hash: str,
    limit: int,
    window_seconds: int,
    block_seconds: int,
) -> RateLimitDecision:
    now = datetime.now(UTC)
    window_cutoff = now - timedelta(seconds=window_seconds)
    blocked_until = now + timedelta(seconds=block_seconds)
    result = await session.execute(
        text(
            """
            INSERT INTO authentication_throttles (
                id, tenant_id, action, key_hash, request_count,
                window_started_at, blocked_until, created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :action, :key_hash, 1,
                :now, NULL, :now, :now
            )
            ON CONFLICT (tenant_id, action, key_hash) DO UPDATE SET
                request_count = CASE
                    WHEN authentication_throttles.window_started_at <= :window_cutoff THEN 1
                    ELSE authentication_throttles.request_count + 1
                END,
                window_started_at = CASE
                    WHEN authentication_throttles.window_started_at <= :window_cutoff THEN :now
                    ELSE authentication_throttles.window_started_at
                END,
                blocked_until = CASE
                    WHEN authentication_throttles.blocked_until > :now
                        THEN authentication_throttles.blocked_until
                    WHEN authentication_throttles.window_started_at <= :window_cutoff THEN NULL
                    WHEN authentication_throttles.request_count >= :request_limit
                        THEN :new_blocked_until
                    ELSE NULL
                END,
                updated_at = :now
            RETURNING blocked_until
            """
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "action": action,
            "key_hash": key_hash,
            "now": now,
            "window_cutoff": window_cutoff,
            "request_limit": max(1, limit),
            "new_blocked_until": blocked_until,
        },
    )
    current_block = result.scalar_one()
    if current_block is None or current_block <= now:
        return RateLimitDecision(allowed=True)
    retry_after = max(1, int((current_block - now).total_seconds()))
    return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)


async def consume_global_rate_limit(
    session: AsyncSession,
    *,
    action: str,
    key_hash: str,
    limit: int,
    window_seconds: int,
    block_seconds: int,
) -> RateLimitDecision:
    now = datetime.now(UTC)
    window_cutoff = now - timedelta(seconds=window_seconds)
    blocked_until = now + timedelta(seconds=block_seconds)
    result = await session.execute(
        text(
            """
            INSERT INTO global_authentication_throttles (
                id, action, key_hash, request_count,
                window_started_at, blocked_until, created_at, updated_at
            ) VALUES (
                :id, :action, :key_hash, 1, :now, NULL, :now, :now
            )
            ON CONFLICT (action, key_hash) DO UPDATE SET
                request_count = CASE
                    WHEN global_authentication_throttles.window_started_at <= :window_cutoff THEN 1
                    ELSE global_authentication_throttles.request_count + 1
                END,
                window_started_at = CASE
                    WHEN global_authentication_throttles.window_started_at <= :window_cutoff THEN :now
                    ELSE global_authentication_throttles.window_started_at
                END,
                blocked_until = CASE
                    WHEN global_authentication_throttles.blocked_until > :now
                        THEN global_authentication_throttles.blocked_until
                    WHEN global_authentication_throttles.window_started_at <= :window_cutoff THEN NULL
                    WHEN global_authentication_throttles.request_count >= :request_limit
                        THEN :new_blocked_until
                    ELSE NULL
                END,
                updated_at = :now
            RETURNING blocked_until
            """
        ),
        {
            "id": uuid.uuid4(),
            "action": action,
            "key_hash": key_hash,
            "now": now,
            "window_cutoff": window_cutoff,
            "request_limit": max(1, limit),
            "new_blocked_until": blocked_until,
        },
    )
    current_block = result.scalar_one()
    if current_block is None or current_block <= now:
        return RateLimitDecision(allowed=True)
    return RateLimitDecision(
        allowed=False,
        retry_after_seconds=max(1, int((current_block - now).total_seconds())),
    )
