from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class ProfileSettings(BaseModel):
    email_idea_updates: bool = True
    email_approval_updates: bool = True
    compact_lists: bool = False
    timezone: Literal[
        "Asia/Kolkata", "UTC", "Europe/London", "America/New_York", "Asia/Singapore"
    ] = "Asia/Kolkata"


class ProfileUpdateCommand(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    settings: ProfileSettings


class ContributionDay(BaseModel):
    date: date
    count: int = Field(ge=0)


class ProfileSummary(BaseModel):
    display_name: str
    email: EmailStr
    tenant_name: str
    roles: list[str]
    settings: ProfileSettings
    contributions: list[ContributionDay]
    total_ideas: int
    submitted_ideas: int
    has_photo: bool
    avatar_updated_at: datetime | None


class ProfilePhotoResult(BaseModel):
    message: str = "Profile photo updated."
    avatar_updated_at: datetime
