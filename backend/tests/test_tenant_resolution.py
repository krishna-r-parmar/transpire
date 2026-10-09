import uuid

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.tenant_context import require_tenant_context
from app.core.tenant_resolution import (
    ResolvedTenant,
    TenantResolutionMiddleware,
    normalize_tenant_slug,
)


def test_normalize_tenant_slug_handles_case_and_whitespace() -> None:
    assert normalize_tenant_slug("  ERC-Group ") == "erc-group"


def test_normalize_tenant_slug_handles_missing_slug() -> None:
    assert normalize_tenant_slug(None) == ""


def test_tenant_path_is_resolved_and_rewritten(monkeypatch) -> None:
    tenant_id = uuid.uuid4()

    async def fake_resolve(slug: str) -> ResolvedTenant | None:
        if slug != "erc-group":
            return None
        return ResolvedTenant(
            tenant_id=tenant_id,
            slug=slug,
            name="ERC Group",
            status="active",
        )

    monkeypatch.setattr("app.core.tenant_resolution.resolve_tenant", fake_resolve)
    application = FastAPI()
    application.add_middleware(TenantResolutionMiddleware, settings=Settings(_env_file=None))

    @application.get("/api/v1/auth/session")
    async def session(request: Request):
        context = require_tenant_context()
        return {
            "slug": request.state.tenant.slug,
            "tenant_id": str(context.tenant_id),
        }

    client = TestClient(application)
    response = client.get("/api/v1/t/erc-group/auth/session")

    assert response.status_code == 200
    assert response.json() == {"slug": "erc-group", "tenant_id": str(tenant_id)}


def test_unscoped_tenant_api_is_rejected() -> None:
    application = FastAPI()
    application.add_middleware(TenantResolutionMiddleware, settings=Settings(_env_file=None))

    @application.get("/api/v1/auth/session")
    async def session():
        return {"unexpected": True}

    response = TestClient(application).get("/api/v1/auth/session")

    assert response.status_code == 404
    assert "tenant_shortname" in response.json()["detail"]
