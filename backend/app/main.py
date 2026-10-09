from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.api import api_router
from app.core.config import get_settings
from app.core.database import close_database
from app.core.health import router as health_router
from app.core.security import CSRFMiddleware, SecurityHeadersMiddleware
from app.core.tenant_resolution import TenantResolutionMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_database()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Tenant-aware API for the TRANSPIRE idea-management platform.",
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.add_middleware(TenantResolutionMiddleware, settings=settings)
    application.add_middleware(CSRFMiddleware, settings=settings)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )
    application.include_router(health_router)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
