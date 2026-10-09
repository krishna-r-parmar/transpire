import uuid

import certifi
import pytest

from app.core.config import Settings
from app.domains.communications.schemas import EmailMessage
from app.domains.communications.services import (
    ConsoleEmailTransport,
    EmailTemplateRenderer,
    SMTPEmailTransport,
    TransactionalEmailService,
)

TEMPLATE_CASES = {
    "invitation": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "inviter_name": "Jordan Lee",
        "expires_in": "48 hours",
        "action_url": "https://example.transpire.test/invitations/accept?token=test",
        "action_label": "Accept invitation",
    },
    "password_reset": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "expires_in": "30 minutes",
        "action_url": "https://example.transpire.test/reset-password?token=test",
        "action_label": "Reset password",
    },
    "idea_submission_confirmation": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "idea_reference": "IDEA-2026-0001",
        "idea_title": "Reduce changeover waiting time",
        "action_url": "https://example.transpire.test/ideas/IDEA-2026-0001",
        "action_label": "View your idea",
    },
    "project_charter_ready": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "idea_reference": "IDEA-2026-0001",
        "idea_title": "Reduce changeover waiting time",
        "action_url": "https://example.transpire.test/ideas/00000000-0000-0000-0000-000000000001?section=project-charter",
        "action_label": "Complete project charter",
    },
    "project_team_invitation": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "project_reference": "PRJ-2026-0001",
        "project_title": "Reduce changeover waiting time",
        "project_lead": "Jordan Lee",
        "action_url": "https://example.transpire.test/projects/00000000-0000-0000-0000-000000000001",
        "action_label": "Review project invitation",
    },
    "account_security": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "event_description": "Your password was changed",
        "event_time": "18 August 2026 at 14:30 IST",
        "action_url": "https://example.transpire.test/account/security",
        "action_label": "Review account security",
    },
    "sso_migration": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "effective_time": "16 September 2026 at 10:30 UTC",
        "action_url": "https://example.transpire.test/t/example/sign-in",
        "action_label": "Sign in with Microsoft",
    },
    "sso_recovery": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "incident_reference": "INC-2041",
        "expires_in": "15 minutes",
        "action_url": "https://example.transpire.test/t/example/admin/sso-recovery?token=test",
        "action_label": "Open restricted recovery",
    },
}


@pytest.mark.parametrize(("template_key", "template_data"), TEMPLATE_CASES.items())
def test_transactional_template_renders_html_and_text(
    template_key: str,
    template_data: dict[str, str],
) -> None:
    rendered = EmailTemplateRenderer().render(
        EmailMessage(
            tenant_id=uuid.uuid4(),
            recipient="avery@example.com",
            template_key=template_key,
            subject="TRANSPIRE notification",
            template_data=template_data,
        )
    )

    assert "Ideate. Transform. Inspire." in rendered.html_body
    assert "Ideate. Transform. Inspire." in rendered.text_body
    assert 'src="http://localhost:3000/brand/transpire-logo.png"' in rendered.html_body
    assert str(template_data["action_url"]) in rendered.html_body
    assert str(template_data["action_url"]) in rendered.text_body
    assert "Avery &lt;script&gt;" in rendered.html_body
    assert "Avery <script>" not in rendered.html_body


def test_renderer_rejects_unknown_template() -> None:
    message = EmailMessage(
        tenant_id=uuid.uuid4(),
        recipient="avery@example.com",
        template_key="unknown",
        subject="Unknown",
    )

    with pytest.raises(ValueError, match="Unsupported email template"):
        EmailTemplateRenderer().render(message)


@pytest.mark.asyncio
async def test_console_transport_returns_correlation_identifier() -> None:
    message = EmailMessage(
        tenant_id=uuid.uuid4(),
        recipient="avery@example.com",
        template_key="password_reset",
        subject="Reset your TRANSPIRE password",
        template_data=TEMPLATE_CASES["password_reset"],
    )
    service = TransactionalEmailService(EmailTemplateRenderer(), ConsoleEmailTransport())

    result = await service.send(message)

    assert result.provider_message_id == f"console:{message.correlation_id}"


@pytest.mark.asyncio
async def test_smtp_transport_uses_certifi_ca_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_options: dict[str, object] = {}

    async def fake_send(*args: object, **kwargs: object) -> None:
        captured_options.update(kwargs)

    monkeypatch.setattr("app.domains.communications.services.aiosmtplib.send", fake_send)
    settings = Settings(EMAIL_BACKEND="smtp", SMTP_HOST="smtp.example.com")
    rendered = EmailTemplateRenderer().render(
        EmailMessage(
            tenant_id=uuid.uuid4(),
            recipient="avery@example.com",
            template_key="password_reset",
            subject="Reset your TRANSPIRE password",
            template_data=TEMPLATE_CASES["password_reset"],
        )
    )

    await SMTPEmailTransport(settings).send(rendered)

    assert captured_options["cert_bundle"] == certifi.where()
