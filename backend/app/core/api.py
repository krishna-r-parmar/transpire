from fastapi import APIRouter

from app.domains.audit.views import router as audit_router
from app.domains.configuration.views import router as configuration_router
from app.domains.ideas.views import admin_router as ideas_admin_router
from app.domains.ideas.views import router as ideas_router
from app.domains.identity.sso_views import router as sso_router
from app.domains.identity.views import router as identity_router
from app.domains.profiles.views import router as profiles_router
from app.domains.projects.views import router as projects_router
from app.domains.tenants.views import router as tenants_router

api_router = APIRouter()
api_router.include_router(audit_router)
api_router.include_router(configuration_router)
api_router.include_router(ideas_admin_router)
api_router.include_router(identity_router)
api_router.include_router(sso_router)
api_router.include_router(profiles_router)
api_router.include_router(projects_router)
api_router.include_router(tenants_router)
api_router.include_router(ideas_router)
