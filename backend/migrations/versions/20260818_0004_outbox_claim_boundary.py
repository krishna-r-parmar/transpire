"""Add the RLS-safe transactional email claim boundary.

Revision ID: 20260818_0004
Revises: 20260818_0003
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0004"
down_revision: str | None = "20260818_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION claim_email_delivery(p_lease_seconds integer)
        RETURNS TABLE (delivery_id uuid, resolved_tenant_id uuid)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        BEGIN
            RETURN QUERY
            WITH candidate AS (
                SELECT email_deliveries.id
                FROM email_deliveries
                WHERE email_deliveries.next_attempt_at <= now()
                  AND (
                    email_deliveries.status = 'queued'::email_delivery_status
                    OR (
                        email_deliveries.status = 'sending'::email_delivery_status
                        AND email_deliveries.locked_at < now() - make_interval(
                            secs => greatest(p_lease_seconds, 30)
                        )
                    )
                  )
                ORDER BY email_deliveries.next_attempt_at, email_deliveries.created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE email_deliveries
            SET status = 'sending'::email_delivery_status,
                attempt_count = email_deliveries.attempt_count + 1,
                locked_at = now(),
                updated_at = now()
            FROM candidate
            WHERE email_deliveries.id = candidate.id
            RETURNING email_deliveries.id, email_deliveries.tenant_id;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS claim_email_delivery(integer)")
