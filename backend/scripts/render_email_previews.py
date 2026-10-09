import uuid
from pathlib import Path

from app.domains.communications.schemas import EmailMessage
from app.domains.communications.services import EmailTemplateRenderer

OUTPUT_DIRECTORY = Path("/tmp/transpire-email-previews")

SAMPLES = {
    "invitation": {
        "recipient_name": "Avery Morgan",
        "tenant_name": "Example Industries",
        "inviter_name": "Jordan Lee",
        "expires_in": "48 hours",
        "action_url": "https://example.transpire.test/invitations/accept",
        "action_label": "Accept invitation",
    },
    "password_reset": {
        "recipient_name": "Avery Morgan",
        "tenant_name": "Example Industries",
        "expires_in": "30 minutes",
        "action_url": "https://example.transpire.test/reset-password",
        "action_label": "Reset password",
    },
    "idea_submission_confirmation": {
        "recipient_name": "Avery Morgan",
        "tenant_name": "Example Industries",
        "idea_reference": "IDEA-2026-0001",
        "idea_title": "Reduce changeover waiting time",
        "action_url": "https://example.transpire.test/ideas/IDEA-2026-0001",
        "action_label": "View your idea",
    },
    "account_security": {
        "recipient_name": "Avery Morgan",
        "tenant_name": "Example Industries",
        "event_description": "Your password was changed",
        "event_time": "18 August 2026 at 14:30 IST",
        "action_url": "https://example.transpire.test/account/security",
        "action_label": "Review account security",
    },
}


def main() -> None:
    renderer = EmailTemplateRenderer()
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    for template_key, template_data in SAMPLES.items():
        rendered = renderer.render(
            EmailMessage(
                tenant_id=uuid.uuid4(),
                recipient="avery@example.com",
                template_key=template_key,
                subject=f"TRANSPIRE · {template_key.replace('_', ' ').title()}",
                template_data=template_data,
            )
        )
        (OUTPUT_DIRECTORY / f"{template_key}.html").write_text(
            rendered.html_body,
            encoding="utf-8",
        )
        (OUTPUT_DIRECTORY / f"{template_key}.txt").write_text(
            rendered.text_body,
            encoding="utf-8",
        )

    print(f"Rendered previews to {OUTPUT_DIRECTORY}")


if __name__ == "__main__":
    main()
