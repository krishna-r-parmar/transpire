import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import Settings

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
CSRF_EXEMPT_SUFFIXES = frozenset(
    {
        "/auth/sign-in",
        "/auth/select-workspace",
        "/auth/password-reset/request",
        "/auth/password-reset/complete",
        "/auth/invitations/accept",
        "/auth/invitations/inspect",
        "/auth/sso/recovery/redeem",
    }
)


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)
        self.session_cookie_name = settings.session_cookie_name
        self.csrf_cookie_name = settings.csrf_cookie_name

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        exempt = any(request.url.path.endswith(suffix) for suffix in CSRF_EXEMPT_SUFFIXES)
        if (
            request.method not in SAFE_METHODS
            and not exempt
            and request.cookies.get(self.session_cookie_name)
        ):
            cookie_token = request.cookies.get(self.csrf_cookie_name, "")
            header_token = request.headers.get("x-csrf-token", "")
            if not cookie_token or not secrets.compare_digest(cookie_token, header_token):
                return JSONResponse(
                    {"detail": "Request security validation failed."},
                    status_code=403,
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
