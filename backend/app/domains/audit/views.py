from typing import Annotated

from fastapi import APIRouter, Query

from app.domains.audit.controllers import list_audit_events
from app.domains.audit.schemas import AuditEventPage
from app.domains.identity.dependencies import (
    AuthenticatedIdentity,
    SessionDependency,
    TenantDependency,
)

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=AuditEventPage)
async def get_audit_events(
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    query: Annotated[str, Query(max_length=120)] = "",
) -> AuditEventPage:
    return await list_audit_events(
        tenant.tenant_id,
        identity.user.id,
        "tenant_admin" in identity.roles,
        session,
        page=page,
        page_size=page_size,
        query=query,
    )
