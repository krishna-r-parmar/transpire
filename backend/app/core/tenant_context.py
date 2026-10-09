import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: uuid.UUID
    slug: str


_current_tenant: ContextVar[TenantContext | None] = ContextVar(
    "current_tenant",
    default=None,
)


def set_tenant_context(context: TenantContext) -> Token[TenantContext | None]:
    return _current_tenant.set(context)


def reset_tenant_context(token: Token[TenantContext | None]) -> None:
    _current_tenant.reset(token)


def require_tenant_context() -> TenantContext:
    context = _current_tenant.get()
    if context is None:
        raise RuntimeError("Tenant context is required for this operation")
    return context


async def apply_tenant_to_transaction(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> None:
    """Expose the verified tenant to PostgreSQL RLS for this transaction only."""

    await session.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
