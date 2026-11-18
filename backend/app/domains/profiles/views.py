from fastapi import APIRouter, HTTPException, Request, Response, status

from app.domains.identity.dependencies import (
    AuthenticatedIdentity,
    SessionDependency,
    TenantDependency,
)
from app.domains.profiles.controllers import (
    InvalidProfilePhotoError,
    mark_tour_seen,
    read_profile,
    read_profile_photo,
    read_tour_progress,
    remove_profile_photo,
    save_profile_photo,
    update_profile,
)
from app.domains.profiles.schemas import (
    ProfilePhotoResult,
    ProfileSummary,
    ProfileUpdateCommand,
    TourId,
    TourProgress,
    TourSeenCommand,
)

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileSummary)
async def get_profile(
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProfileSummary:
    return await read_profile(
        tenant.tenant_id, identity.tenant.name, identity.user.id, identity.roles, session
    )


@router.patch("", response_model=ProfileSummary)
async def patch_profile(
    command: ProfileUpdateCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProfileSummary:
    return await update_profile(
        tenant.tenant_id,
        identity.tenant.name,
        identity.user.id,
        identity.roles,
        command,
        session,
    )


@router.get("/photo", response_class=Response)
async def get_profile_photo(
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> Response:
    try:
        data, content_type, updated_at = await read_profile_photo(
            tenant.tenant_id, identity.user.id, session
        )
    except InvalidProfilePhotoError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "ETag": f'"{int(updated_at.timestamp())}"',
        },
    )


@router.put("/photo", response_model=ProfilePhotoResult)
async def put_profile_photo(
    request: Request,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> ProfilePhotoResult:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Choose an image smaller than 2 MB.")
    try:
        return await save_profile_photo(
            tenant.tenant_id,
            identity.user.id,
            request.headers.get("content-type", "").split(";", 1)[0],
            await request.body(),
            session,
        )
    except InvalidProfilePhotoError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/photo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile_photo(
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> Response:
    await remove_profile_photo(tenant.tenant_id, identity.user.id, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tours", response_model=TourProgress)
async def get_tour_progress(
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> TourProgress:
    return await read_tour_progress(tenant.tenant_id, identity.user.id, session)


@router.put("/tours/{tour_id}", response_model=TourProgress)
async def put_tour_seen(
    tour_id: TourId,
    command: TourSeenCommand,
    identity: AuthenticatedIdentity,
    tenant: TenantDependency,
    session: SessionDependency,
) -> TourProgress:
    return await mark_tour_seen(
        tenant.tenant_id, identity.user.id, tour_id, command.version, session
    )
