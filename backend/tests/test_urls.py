from app.core.config import Settings
from app.core.urls import platform_frontend_url, tenant_frontend_url


def test_platform_frontend_url_keeps_configured_local_origin() -> None:
    settings = Settings(PUBLIC_APP_URL="http://localhost:3000/")

    result = platform_frontend_url(
        settings,
        "/accept-invitation",
        query={"token": "safe-test-token"},
    )

    assert result == ("http://localhost:3000/accept-invitation?token=safe-test-token")


def test_platform_frontend_url_keeps_configured_production_origin() -> None:
    settings = Settings(PUBLIC_APP_URL="https://transpire.example.com")

    result = platform_frontend_url(settings, "/sign-in")

    assert result == "https://transpire.example.com/sign-in"


def test_tenant_frontend_url_uses_shared_origin_and_workspace_shortname() -> None:
    settings = Settings(PUBLIC_APP_URL="https://transpire.example.com")

    result = tenant_frontend_url(settings, "acme", "/sign-in")

    assert result == "https://transpire.example.com/t/acme/sign-in"


def test_tenant_frontend_url_retains_development_port() -> None:
    settings = Settings(PUBLIC_APP_URL="http://localhost:3000")

    result = tenant_frontend_url(settings, "acme", "/sign-in")

    assert result == "http://localhost:3000/t/acme/sign-in"
