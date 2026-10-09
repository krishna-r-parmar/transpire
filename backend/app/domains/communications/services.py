import logging
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
SUPPORTED_TEMPLATES = frozenset(
    {
        "account_security",
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
    ) -> None:
        self.logo_url = f"{public_app_url.rstrip('/')}/brand/transpire-logo.png"
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
