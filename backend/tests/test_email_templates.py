import uuid
from email.message import EmailMessage as MIMEEmailMessage

import certifi
import pytest

from app.core.config import Settings
from app.domains.communications.schemas import EmailMessage
from app.domains.communications.services import (
    FOOTER_IMAGE,
    INLINE_IMAGES,
    LOGO_IMAGE,
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
        "secondary_url": "https://example.transpire.test/t/example/profile",
        "secondary_label": "Manage preferences",
    },
    "project_charter_ready": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "idea_reference": "IDEA-2026-0001",
        "idea_title": "Reduce changeover waiting time",
        "action_url": "https://example.transpire.test/ideas/00000000-0000-0000-0000-000000000001?section=project-charter",
        "action_label": "Complete project charter",
        "secondary_url": "https://example.transpire.test/t/example/profile",
        "secondary_label": "Manage preferences",
    },
    "project_team_invitation": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "project_reference": "PRJ-2026-0001",
        "project_title": "Reduce changeover waiting time",
        "project_lead": "Jordan Lee",
        "action_url": "https://example.transpire.test/projects/00000000-0000-0000-0000-000000000001",
        "action_label": "Review project invitation",
        "secondary_url": "https://example.transpire.test/t/example/profile",
        "secondary_label": "Manage preferences",
    },
    "account_security": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "event_description": "Your password was changed",
        "event_time": "18 August 2026 at 14:30 IST",
        "action_url": "https://example.transpire.test/account/security",
        "action_label": "Review account security",
        "secondary_url": "https://example.transpire.test/t/example/profile",
        "secondary_label": "Manage preferences",
    },
    "check_in_reminder": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "action_url": "https://example.transpire.test/t/example/sign-in",
        "action_label": "Sign in to TRANSPIRE",
        "secondary_url": "https://example.transpire.test/t/example/profile",
        "secondary_label": "Manage preferences",
    },
    "sso_migration": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "effective_time": "16 September 2026 at 10:30 UTC",
        "action_url": "https://example.transpire.test/t/example/sign-in",
        "action_label": "Sign in with Microsoft",
        "secondary_url": "https://example.transpire.test/t/example/profile",
        "secondary_label": "Manage preferences",
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
    assert f'src="cid:{LOGO_IMAGE.content_id}"' in rendered.html_body
    assert f"cid:{FOOTER_IMAGE.content_id}" in rendered.html_body
    assert str(template_data["action_url"]) in rendered.html_body
    assert str(template_data["action_url"]) in rendered.text_body
    assert "<script>" not in rendered.html_body
    assert str(template_data["action_label"]) in rendered.html_body
    if "secondary_url" in template_data:
        assert "Manage preferences" in rendered.html_body
        assert str(template_data["secondary_url"]) in rendered.text_body
    else:
        assert "Manage preferences" not in rendered.html_body
        assert "Automated message from TRANSPIRE" in rendered.html_body


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
@pytest.mark.parametrize("port", [25, 587])
async def test_smtp_transport_uses_certifi_ca_bundle(
    monkeypatch: pytest.MonkeyPatch, port: int
) -> None:
    captured_options: dict[str, object] = {}

    async def fake_send(*args: object, **kwargs: object) -> None:
        captured_options.update(kwargs)

    monkeypatch.setattr("app.domains.communications.services.aiosmtplib.send", fake_send)
    settings = Settings(
        EMAIL_BACKEND="smtp", SMTP_HOST="smtp.example.com", SMTP_PORT=port,
        SMTP_USERNAME="", SMTP_PASSWORD="", SMTP_START_TLS=True, SMTP_USE_TLS=False,
    )
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
    assert captured_options["port"] == port
    assert captured_options["username"] is None
    assert captured_options["password"] is None
    assert captured_options["start_tls"] is True
    assert captured_options["use_tls"] is False


def test_preview_renderer_links_brand_images_from_public_url() -> None:
    renderer = EmailTemplateRenderer(
        public_app_url="https://transpire.example.com/", inline_images=False
    )
    rendered = renderer.render(
        EmailMessage(
            tenant_id=uuid.uuid4(),
            recipient="avery@example.com",
            template_key="password_reset",
            subject="Reset your TRANSPIRE password",
            template_data=TEMPLATE_CASES["password_reset"],
        )
    )

    assert 'src="https://transpire.example.com/brand/transpire-logo.png"' in rendered.html_body
    assert "https://transpire.example.com/brand/transpire-email-footer-connected-ideas.jpg" in (
        rendered.html_body
    )
    assert "cid:" not in rendered.html_body


def test_inline_brand_images_are_bundled_with_the_backend() -> None:
    for image in INLINE_IMAGES:
        assert image.path.is_file(), image.path
        # Keep each embedded image small: it is sent with every email.
        assert image.path.stat().st_size < 100_000


@pytest.mark.asyncio
async def test_smtp_transport_embeds_brand_images_as_related_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[MIMEEmailMessage] = []

    async def fake_send(message: MIMEEmailMessage, **_: object) -> None:
        sent.append(message)

    monkeypatch.setattr("app.domains.communications.services.aiosmtplib.send", fake_send)
    settings = Settings(EMAIL_BACKEND="smtp", SMTP_HOST="smtp.example.com", SMTP_PORT=25)
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

    (mime,) = sent
    assert mime.get_content_type() == "multipart/alternative"
    text_part, related = mime.iter_parts()
    assert text_part.get_content_type() == "text/plain"
    assert related.get_content_type() == "multipart/related"
    html_part, *images = related.iter_parts()
    assert html_part.get_content_type() == "text/html"
    assert {image["Content-ID"] for image in images} == {
        f"<{LOGO_IMAGE.content_id}>",
        f"<{FOOTER_IMAGE.content_id}>",
    }
    assert {image.get_content_type() for image in images} == {"image/png", "image/jpeg"}
    assert all(image.get_content_disposition() == "inline" for image in images)
    assert images[0].get_content() == LOGO_IMAGE.path.read_bytes()


def test_check_in_reminder_puts_actions_first_and_greets_by_first_name() -> None:
    renderer = EmailTemplateRenderer()
    data = TEMPLATE_CASES["check_in_reminder"]
    rendered = renderer.render(
        EmailMessage(
            tenant_id=uuid.uuid4(),
            recipient="avery@example.com",
            template_key="check_in_reminder",
            subject="Reminder: check in to Example Industries on TRANSPIRE",
            template_data=data,
        )
    )
    assert "Manage preferences" in rendered.html_body
    assert "/t/example/profile" in rendered.html_body
    # Both buttons come before the "What you can do today" cards.
    assert rendered.html_body.index("Sign in to TRANSPIRE") < rendered.html_body.index("Share an idea")
    assert "Time to check in, Avery." in rendered.text_body

    hostile = renderer.render(
        EmailMessage(
            tenant_id=uuid.uuid4(),
            recipient="avery@example.com",
            template_key="check_in_reminder",
            subject="Reminder",
            template_data={**data, "recipient_name": "<img>Avery Lee"},
        )
    )
    assert "Time to check in, &lt;img&gt;Avery." in hostile.html_body


def test_detail_values_and_first_names_are_escaped() -> None:
    rendered = EmailTemplateRenderer().render(
        EmailMessage(
            tenant_id=uuid.uuid4(),
            recipient="avery@example.com",
            template_key="project_charter_ready",
            subject="Your idea IDEA-2026-0001 is approved",
            template_data={
                **TEMPLATE_CASES["project_charter_ready"],
                "recipient_name": "<i>Avery Lee",
                "idea_title": "<b>Faster</b> changeovers",
            },
        )
    )
    assert "&lt;b&gt;Faster&lt;/b&gt; changeovers" in rendered.html_body
    assert "Great news, &lt;i&gt;Avery." in rendered.html_body
    assert "<b>Faster</b>" not in rendered.html_body
