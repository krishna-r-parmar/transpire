import uuid

from pydantic import BaseModel, EmailStr, Field


class EmailMessage(BaseModel):
    tenant_id: uuid.UUID
    recipient: EmailStr
    template_key: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=250)
    template_data: dict[str, object] = Field(default_factory=dict)
    correlation_id: uuid.UUID = Field(default_factory=uuid.uuid4)


class EmailSendResult(BaseModel):
    provider_message_id: str


class RenderedEmail(BaseModel):
    tenant_id: uuid.UUID
    recipient: EmailStr
    subject: str
    html_body: str
    text_body: str
    correlation_id: uuid.UUID
