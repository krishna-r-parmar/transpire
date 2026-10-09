import uuid
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import Settings
from app.core.database import engine
from app.core.tenant_context import TenantContext, reset_tenant_context, set_tenant_context


@dataclass(frozen=True, slots=True)
class ResolvedTenant:
    tenant_id: uuid.UUID
    slug: str
    name: str
    status: str


def normalize_tenant_slug(slug: str | None) -> str:
    if not slug:
        return ""
    return slug.strip().lower()


async def resolve_tenant(slug: str) -> ResolvedTenant | None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT * FROM resolve_tenant_by_slug(:slug)"),
            {"slug": slug},
        )
        row = result.mappings().one_or_none()

    if row is None:
        return None
    return ResolvedTenant(
        tenant_id=row["tenant_id"],
        name=row["name"],
        status=row["status"],
        slug=row["slug"],
    )


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)
        self.tenant_prefixes = tuple(
            f"{settings.api_v1_prefix}/{segment}"
            for segment in (
                "auth",
                "admin",
                "platform",
                "ideas",
                "projects",
                "profile",
                "audit",
            )
        )
        self.api_v1_prefix = settings.api_v1_prefix.rstrip("/")
        self.tenant_path_prefix = f"{self.api_v1_prefix}/t/"
        self.global_auth_paths = {
            f"{self.api_v1_prefix}/auth/sign-in",
            f"{self.api_v1_prefix}/auth/select-workspace",
            f"{self.api_v1_prefix}/auth/password-reset/request",
        }
        self.global_auth_prefixes = (
            f"{self.api_v1_prefix}/auth/invitations/",
            f"{self.api_v1_prefix}/auth/sso/global/",
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        original_path = request.scope.get("path", "")
        if original_path in self.global_auth_paths or original_path.startswith(
            self.global_auth_prefixes
        ):
            return await call_next(request)

        if original_path.startswith(self.tenant_path_prefix):
            tenant_path = original_path[len(self.tenant_path_prefix) :]
            slug, separator, remainder = tenant_path.partition("/")
            if not separator or not remainder:
                return JSONResponse(
                    {"detail": "A tenant shortname is required in the request path."},
                    status_code=404,
                )
            routed_path = f"{self.api_v1_prefix}/{remainder}"
            if not routed_path.startswith(self.tenant_prefixes):
                return await call_next(request)
        elif original_path.startswith(self.tenant_prefixes):
            return JSONResponse(
                {"detail": "Use /api/v1/t/{tenant_shortname} for tenant requests."},
                status_code=404,
            )
        else:
            return await call_next(request)

        slug = normalize_tenant_slug(slug)
        try:
            tenant = await resolve_tenant(slug)
        except SQLAlchemyError:
            return JSONResponse(
                {"detail": "Authentication service is temporarily unavailable."},
                status_code=503,
            )

        if tenant is None:
            return JSONResponse(
                {"detail": "TRANSPIRE workspace was not found for this shortname."},
                status_code=404,
            )
        if tenant.status != "active":
            return JSONResponse(
                {"detail": "This TRANSPIRE workspace is currently unavailable."},
                status_code=403,
            )

        request.state.tenant = tenant
        token = set_tenant_context(
            TenantContext(tenant_id=tenant.tenant_id, slug=tenant.slug)
        )
        request.scope["path"] = routed_path
        request.scope["raw_path"] = routed_path.encode("utf-8")
        try:
            return await call_next(request)
        finally:
            reset_tenant_context(token)


def get_resolved_tenant(request: Request) -> ResolvedTenant:
    tenant = getattr(request.state, "tenant", None)
    if not isinstance(tenant, ResolvedTenant):
        raise TypeError("Resolved tenant is required for authentication")
    return tenant
