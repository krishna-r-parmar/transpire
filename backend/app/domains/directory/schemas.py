import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DirectorySettings(BaseModel):
    """Per-workspace HR directory behaviour, stored in tenant settings."""

    # Approvers (anyone listed as a reporting manager or HoD) are always invited, because
    # workflows depend on them. Inviting every other employee is opt-in, so a first load
    # never emails the whole company by accident.
    invite_new_employees: bool = False
    # Empty means any domain. Otherwise only these company domains get accounts.
    allowed_email_domains: list[str] = Field(default_factory=list, max_length=20)
    # Block a file when more than this share of active employees disappears at once.
    max_drop_percent: int = Field(default=10, ge=1, le=100)

    @field_validator("allowed_email_domains")
    @classmethod
    def clean_domains(cls, domains: list[str]) -> list[str]:
        cleaned = []
        for domain in domains:
            value = domain.strip().casefold().lstrip("@")
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned


class DirectoryOverview(BaseModel):
    settings: DirectorySettings
    inbox_folder: str
    inbox_waiting: list[str]
    employees_active: int
    employees_missing: int
    employees_left: int
    employees_with_account: int
    last_applied_at: datetime | None


class DirectoryRunSummary(BaseModel):
    id: uuid.UUID
    file_name: str
    source: str
    status: str
    created_at: datetime
    summary: dict[str, object]
    report: dict[str, object]


class DirectoryEmployeeSummary(BaseModel):
    employee_id: str
    display_name: str
    email: str | None
    location: str
    department: str
    sub_department: str
    manager_employee_id: str | None
    manager_name: str | None
    hod_employee_id: str | None
    hod_name: str | None
    status: str
    has_account: bool


class SftpSourceView(BaseModel):
    """What administrators see. The secret is never returned, only whether one is stored."""

    enabled: bool
    host: str
    port: int
    username: str
    auth_method: str
    has_secret: bool
    remote_path: str
    trusted_fingerprint: str | None
    presented_fingerprint: str | None
    key_awaiting_trust: bool
    last_run_at: datetime | None
    last_status: str | None
    last_message: str | None


class SftpSourceCommand(BaseModel):
    enabled: bool = False
    host: str = Field(default="", max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(default="", max_length=120)
    auth_method: str = Field(default="password", pattern="^(password|private_key)$")
    # Leave empty to keep the stored password or key.
    secret: str | None = Field(default=None, max_length=16000)
    remote_path: str = Field(default="", max_length=500)


class TrustHostKeyCommand(BaseModel):
    fingerprint: str = Field(min_length=10, max_length=200)


class SftpActionResult(BaseModel):
    ok: bool
    message: str
    source: SftpSourceView
    run: DirectoryRunSummary | None = None
