import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AuditEventRecord(BaseModel):
    id: uuid.UUID
    event_type: str
    entity_type: str
    entity_id: uuid.UUID | None
    entity_reference: str | None
    summary: str
    details: dict[str, object]
    actor_name: str | None
    actor_email: str | None
    subject_name: str | None
    created_at: datetime


class AuditEventPage(BaseModel):
    items: list[AuditEventRecord]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    tenant_scope: bool
