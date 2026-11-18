import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage as MIMEEmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Protocol

import aiosmtplib
import certifi
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.config import Settings, get_settings
from app.domains.communications.schemas import (
    EmailMessage,
    EmailSendResult,
    RenderedEmail,
)

logger = logging.getLogger(__name__)
TEMPLATE_ROOT = Path(__file__).with_name("templates")
ASSET_ROOT = Path(__file__).with_name("assets")


@dataclass(frozen=True, slots=True)
class InlineImage:
    """A brand image sent inside the email, referenced from the HTML as ``cid:<content_id>``."""

    content_id: str
    path: Path
    subtype: str


# Embedded rather than linked, so they show without a reachable PUBLIC_APP_URL and
# without Outlook's "download pictures" prompt.
LOGO_IMAGE = InlineImage("transpire-logo@transpire.email", ASSET_ROOT / "transpire-logo.png", "png")
FOOTER_IMAGE = InlineImage(
    "transpire-footer@transpire.email", ASSET_ROOT / "transpire-email-footer.jpg", "jpeg"
)
INLINE_IMAGES = (LOGO_IMAGE, FOOTER_IMAGE)
SUPPORTED_TEMPLATES = frozenset(
    {
        "account_security",
        "approval_escalation",
        "approval_overdue",
        "approval_request",
        "approval_withdrawn",
        "check_in_reminder",
        "comment_posted",
        "comment_request",
        "idea_needs_correction",
        "idea_rejected",
        "privileged_role_granted",
        "role_changed",
        "idea_submission_confirmation",
        "invitation",
        "password_reset",
        "project_charter_ready",
        "project_team_invitation",
        "sso_migration",
        "sso_recovery",
    }
)


class EmailTemplateRenderer:
    def __init__(
        self,
        template_root: Path = TEMPLATE_ROOT,
        public_app_url: str = "http://localhost:3000",
        *,
        inline_images: bool = True,
    ) -> None:
        """``inline_images`` points the HTML at embedded ``cid:`` images, for sending.
        Pass False for browser previews, which can't resolve ``cid:`` and use the public URLs.
        """
        if inline_images:
            self.logo_url = f"cid:{LOGO_IMAGE.content_id}"
            self.footer_image_url = f"cid:{FOOTER_IMAGE.content_id}"
        else:
            brand_url = f"{public_app_url.rstrip('/')}/brand"
            self.logo_url = f"{brand_url}/transpire-logo.png"
            self.footer_image_url = f"{brand_url}/transpire-email-footer-connected-ideas.jpg"
        self.environment = Environment(
            loader=FileSystemLoader(template_root),
            autoescape=select_autoescape(("html", "xml")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, message: EmailMessage) -> RenderedEmail:
        if message.template_key not in SUPPORTED_TEMPLATES:
            raise ValueError(f"Unsupported email template: {message.template_key}")

        context = {
            **message.template_data,
            "subject": message.subject,
            "current_year": datetime.now(UTC).year,
            "logo_url": self.logo_url,
            "footer_image_url": self.footer_image_url,
        }
        html_body = self.environment.get_template(f"{message.template_key}.html").render(context)
        text_body = self.environment.get_template(f"{message.template_key}.txt").render(context)
        return RenderedEmail(
            tenant_id=message.tenant_id,
            recipient=message.recipient,
            subject=message.subject,
            html_body=html_body,
            text_body=text_body,
            correlation_id=message.correlation_id,
        )


class EmailTransport(Protocol):
    async def send(self, message: RenderedEmail) -> EmailSendResult: ...


class ConsoleEmailTransport:
    """Safe local adapter that records metadata without exposing rendered content."""

    async def send(self, message: RenderedEmail) -> EmailSendResult:
        provider_message_id = f"console:{message.correlation_id}"
        logger.info(
            "Captured development email",
            extra={
                "tenant_id": str(message.tenant_id),
                "recipient": str(message.recipient),
                "correlation_id": str(message.correlation_id),
            },
        )
        return EmailSendResult(provider_message_id=provider_message_id)


def attach_inline_images(mime: MIMEEmailMessage, html_body: str) -> None:
    """Attach each brand image the HTML references, turning the HTML part into multipart/related."""
    html_part = mime.get_body(preferencelist=("html",))
    if html_part is None:
        return
    for image in INLINE_IMAGES:
        if f"cid:{image.content_id}" not in html_body:
            continue
        html_part.add_related(
            image.path.read_bytes(),
            maintype="image",
            subtype=image.subtype,
            cid=f"<{image.content_id}>",
            disposition="inline",
            filename=image.path.name,
        )


class SMTPEmailTransport:
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host:
            raise ValueError("SMTP_HOST is required when EMAIL_BACKEND=smtp")
        if settings.smtp_start_tls and settings.smtp_use_tls:
            raise ValueError("SMTP_START_TLS and SMTP_USE_TLS cannot both be enabled")
        self.settings = settings

    async def send(self, message: RenderedEmail) -> EmailSendResult:
        mime = MIMEEmailMessage()
        mime["From"] = formataddr(
            (self.settings.email_from_name, str(self.settings.email_from_address))
        )
        mime["To"] = str(message.recipient)
        mime["Subject"] = message.subject
        mime["X-TRANSPIRE-Correlation-ID"] = str(message.correlation_id)
        mime.set_content(message.text_body)
        mime.add_alternative(message.html_body, subtype="html")
        attach_inline_images(mime, message.html_body)

        await aiosmtplib.send(
            mime,
            hostname=self.settings.smtp_host,
            port=self.settings.smtp_port,
            username=self.settings.smtp_username or None,
            password=self.settings.smtp_password.get_secret_value() or None,
            start_tls=self.settings.smtp_start_tls,
            use_tls=self.settings.smtp_use_tls,
            timeout=self.settings.smtp_timeout_seconds,
            cert_bundle=certifi.where(),
        )
        return EmailSendResult(provider_message_id=f"smtp:{message.correlation_id}")


class TransactionalEmailService:
    def __init__(self, renderer: EmailTemplateRenderer, transport: EmailTransport) -> None:
        self.renderer = renderer
        self.transport = transport

    async def send(self, message: EmailMessage) -> EmailSendResult:
        rendered = self.renderer.render(message)
        return await self.transport.send(rendered)


def build_email_service(settings: Settings | None = None) -> TransactionalEmailService:
    resolved_settings = settings or get_settings()
    if resolved_settings.email_backend == "console":
        transport: EmailTransport = ConsoleEmailTransport()
    elif resolved_settings.email_backend == "smtp":
        transport = SMTPEmailTransport(resolved_settings)
    else:
        raise ValueError(f"Unsupported EMAIL_BACKEND: {resolved_settings.email_backend}")

    return TransactionalEmailService(
        EmailTemplateRenderer(public_app_url=resolved_settings.public_app_url), transport
    )
