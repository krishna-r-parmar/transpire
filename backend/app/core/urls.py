from urllib.parse import urlencode, urlsplit, urlunsplit

from app.core.config import Settings


def platform_frontend_url(
    settings: Settings,
    path: str,
    *,
    query: dict[str, str] | None = None,
) -> str:
    base = urlsplit(settings.public_app_url)
    return urlunsplit(
        (
            base.scheme,
            base.netloc,
            path,
            urlencode(query or {}),
            "",
        )
    )


def tenant_frontend_url(
    settings: Settings,
    tenant_slug: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
) -> str:
    base = urlsplit(settings.public_app_url)
    tenant_path = f"/t/{tenant_slug}{path if path.startswith('/') else f'/{path}'}"
    return urlunsplit(
        (
            base.scheme,
            base.netloc,
            tenant_path,
            urlencode(query or {}),
            "",
        )
    )
