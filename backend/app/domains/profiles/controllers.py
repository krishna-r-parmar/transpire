import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.ideas.models import Idea, IdeaStatus
from app.domains.identity.models import User
from app.domains.profiles.schemas import (
    ContributionDay,
    ProfilePhotoResult,
    ProfileSettings,
    ProfileSummary,
    ProfileUpdateCommand,
)

MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024


class InvalidProfilePhotoError(Exception):
    pass


def _detected_image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def read_profile(
    tenant_id: uuid.UUID,
    tenant_name: str,
    user_id: uuid.UUID,
    roles: list[str],
    session: AsyncSession,
) -> ProfileSummary:
    first_day = datetime.now(UTC).date() - timedelta(days=364)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        user = await session.get(User, user_id)
        submitted_dates = list(
            (
                await session.scalars(
                    select(Idea.submitted_at).where(
                        Idea.tenant_id == tenant_id,
                        Idea.submitter_user_id == user_id,
                        Idea.submitted_at.is_not(None),
                        Idea.submitted_at >= datetime.combine(first_day, datetime.min.time(), UTC),
                    )
                )
            ).all()
        )
        statuses = list(
            (
                await session.scalars(
                    select(Idea.status).where(
                        Idea.tenant_id == tenant_id,
                        Idea.submitter_user_id == user_id,
                    )
                )
            ).all()
        )
        counts = Counter(value.date() for value in submitted_dates if value)
        settings = ProfileSettings.model_validate(user.profile_settings or {})
        return ProfileSummary(
            display_name=user.display_name,
            email=user.email,
            tenant_name=tenant_name,
            roles=roles,
            settings=settings,
            contributions=[
                ContributionDay(date=day, count=counts[day])
                for offset in range(365)
                if (day := first_day + timedelta(days=offset))
            ],
            total_ideas=len(statuses),
            submitted_ideas=sum(status != IdeaStatus.DRAFT for status in statuses),
            has_photo=user.avatar_data is not None,
            avatar_updated_at=user.avatar_updated_at,
        )


async def update_profile(
    tenant_id: uuid.UUID,
    tenant_name: str,
    user_id: uuid.UUID,
    roles: list[str],
    command: ProfileUpdateCommand,
    session: AsyncSession,
) -> ProfileSummary:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        user = await session.get(User, user_id)
        user.display_name = command.display_name.strip()
        user.profile_settings = command.settings.model_dump()
    return await read_profile(tenant_id, tenant_name, user_id, roles, session)


async def save_profile_photo(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    content_type: str,
    data: bytes,
    session: AsyncSession,
) -> ProfilePhotoResult:
    detected_type = _detected_image_type(data)
    if not data or len(data) > MAX_PROFILE_PHOTO_BYTES:
        raise InvalidProfilePhotoError("Choose an image smaller than 2 MB.")
    if detected_type is None or detected_type != content_type.casefold():
        raise InvalidProfilePhotoError("Choose a valid JPEG, PNG, or WebP image.")
    now = datetime.now(UTC)
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        user = await session.get(User, user_id)
        user.avatar_data = data
        user.avatar_content_type = detected_type
        user.avatar_updated_at = now
    return ProfilePhotoResult(avatar_updated_at=now)


async def remove_profile_photo(
    tenant_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> None:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        user = await session.get(User, user_id)
        user.avatar_data = None
        user.avatar_content_type = None
        user.avatar_updated_at = None


async def read_profile_photo(
    tenant_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> tuple[bytes, str, datetime]:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        user = await session.get(User, user_id)
        if user.avatar_data is None or user.avatar_content_type is None:
            raise InvalidProfilePhotoError("Profile photo not found.")
        return user.avatar_data, user.avatar_content_type, user.avatar_updated_at or user.updated_at
