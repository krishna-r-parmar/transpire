from functools import lru_cache
from pathlib import Path

from pydantic import EmailStr, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "TRANSPIRE API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+asyncpg://transpire:change-me@localhost:5432/transpire",
        validation_alias="DATABASE_URL",
    )
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )
    cors_origin_regex: str = Field(
        default="",
        validation_alias="CORS_ORIGIN_REGEX",
    )
    allowed_hosts: str = Field(
        default="localhost,127.0.0.1,testserver",
        validation_alias="ALLOWED_HOSTS",
    )
    email_backend: str = Field(default="console", validation_alias="EMAIL_BACKEND")
    email_from_address: EmailStr = Field(
        default="no-reply@transpire.example.com",
        validation_alias="EMAIL_FROM_ADDRESS",
    )
    email_from_name: str = Field(default="TRANSPIRE", validation_alias="EMAIL_FROM_NAME")
    public_app_url: str = Field(
        default="http://localhost:3000",
        validation_alias="PUBLIC_APP_URL",
    )
    public_api_url: str = Field(
        default="http://localhost:8000/api/v1",
        validation_alias="PUBLIC_API_URL",
    )
    fx_api_base_url: str = Field(
        default="https://api.frankfurter.dev/v2",
        validation_alias="FX_API_BASE_URL",
    )
    fx_cache_minutes: int = Field(default=360, validation_alias="FX_CACHE_MINUTES")
    smtp_host: str = Field(default="", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_username: str = Field(default="", validation_alias="SMTP_USERNAME")
    smtp_password: SecretStr = Field(default=SecretStr(""), validation_alias="SMTP_PASSWORD")
    smtp_start_tls: bool = Field(default=True, validation_alias="SMTP_START_TLS")
    smtp_use_tls: bool = Field(default=False, validation_alias="SMTP_USE_TLS")
    smtp_timeout_seconds: float = Field(default=15.0, validation_alias="SMTP_TIMEOUT_SECONDS")
    session_cookie_name: str = Field(
        default="transpire_session",
        validation_alias="SESSION_COOKIE_NAME",
    )
    csrf_cookie_name: str = Field(
        default="transpire_csrf",
        validation_alias="CSRF_COOKIE_NAME",
    )
    sso_selection_cookie_name: str = Field(
        default="transpire_sso_selection",
        validation_alias="SSO_SELECTION_COOKIE_NAME",
    )
    session_cookie_secure: bool = Field(
        default=False,
        validation_alias="SESSION_COOKIE_SECURE",
    )
    session_hours: int = Field(default=12, validation_alias="SESSION_HOURS")
    remembered_session_days: int = Field(
        default=30,
        validation_alias="REMEMBERED_SESSION_DAYS",
    )
    password_reset_minutes: int = Field(
        default=30,
        validation_alias="PASSWORD_RESET_MINUTES",
    )
    invitation_expiry_hours: int = Field(
        default=48,
        validation_alias="INVITATION_EXPIRY_HOURS",
    )
    sign_in_rate_limit: int = Field(default=10, validation_alias="SIGN_IN_RATE_LIMIT")
    password_reset_rate_limit: int = Field(
        default=5,
        validation_alias="PASSWORD_RESET_RATE_LIMIT",
    )
    auth_rate_window_seconds: int = Field(
        default=900,
        validation_alias="AUTH_RATE_WINDOW_SECONDS",
    )
    auth_rate_block_seconds: int = Field(
        default=900,
        validation_alias="AUTH_RATE_BLOCK_SECONDS",
    )
    account_lockout_attempts: int = Field(
        default=5,
        validation_alias="ACCOUNT_LOCKOUT_ATTEMPTS",
    )
    account_lockout_minutes: int = Field(
        default=15,
        validation_alias="ACCOUNT_LOCKOUT_MINUTES",
    )
    workspace_selection_minutes: int = Field(
        default=5,
        validation_alias="WORKSPACE_SELECTION_MINUTES",
    )
    entra_client_id: str = Field(default="", validation_alias="ENTRA_CLIENT_ID")
    entra_client_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="ENTRA_CLIENT_SECRET"
    )
    oidc_state_minutes: int = Field(default=10, validation_alias="OIDC_STATE_MINUTES")
    sso_recovery_minutes: int = Field(default=15, validation_alias="SSO_RECOVERY_MINUTES")
    outbox_encryption_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="OUTBOX_ENCRYPTION_KEY",
    )
    outbox_max_attempts: int = Field(
        default=5,
        validation_alias="OUTBOX_MAX_ATTEMPTS",
    )
    outbox_retry_base_seconds: int = Field(
        default=30,
        validation_alias="OUTBOX_RETRY_BASE_SECONDS",
    )
    outbox_lease_seconds: int = Field(
        default=300,
        validation_alias="OUTBOX_LEASE_SECONDS",
    )
    development_tenant_slug: str = Field(
        default="transpire-local",
        validation_alias="DEV_TENANT_SLUG",
    )
    development_tenant_name: str = Field(
        default="TRANSPIRE Local",
        validation_alias="DEV_TENANT_NAME",
    )
    development_admin_email: EmailStr = Field(
        default="admin@transpire.example.com",
        validation_alias="DEV_ADMIN_EMAIL",
    )
    development_admin_name: str = Field(
        default="TRANSPIRE Administrator",
        validation_alias="DEV_ADMIN_NAME",
    )
    development_admin_password: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="DEV_ADMIN_PASSWORD",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment.casefold() != "production":
            return self
        if not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        if not self.outbox_encryption_key.get_secret_value():
            raise ValueError("OUTBOX_ENCRYPTION_KEY is required in production")
        if "*" in self.trusted_hosts:
            raise ValueError("ALLOWED_HOSTS cannot contain * in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
