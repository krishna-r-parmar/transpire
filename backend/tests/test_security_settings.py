import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.domains.tenants.schemas import TenantCreate


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ENVIRONMENT": "production",
        "SESSION_COOKIE_SECURE": True,
        "OUTBOX_ENCRYPTION_KEY": "valid-production-outbox-key",
        "ALLOWED_HOSTS": "transpire.example.com,api.transpire.example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "override",
    [
        {"SESSION_COOKIE_SECURE": False},
        {"OUTBOX_ENCRYPTION_KEY": ""},
        {"ALLOWED_HOSTS": "*"},
    ],
)
def test_production_rejects_unsafe_security_configuration(
    override: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        production_settings(**override)


def test_production_accepts_explicit_secure_configuration() -> None:
    settings = production_settings()
    assert settings.session_cookie_secure is True
    assert settings.trusted_hosts == ["transpire.example.com", "api.transpire.example.com"]


@pytest.mark.parametrize(
    "slug",
    ["Company", "company.example.com", "-company", "company_"],
)
def test_tenant_shortname_rejects_invalid_values(slug: str) -> None:
    with pytest.raises(ValidationError):
        TenantCreate(slug=slug, name="Company")
