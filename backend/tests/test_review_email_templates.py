import uuid

import pytest

from app.domains.communications.schemas import EmailMessage
from app.domains.communications.services import EmailTemplateRenderer

PREFS = {
    "secondary_url": "https://example.transpire.test/t/example/profile",
    "secondary_label": "Manage preferences",
}
IDEA = {
    "recipient_name": "Avery <script>",
    "tenant_name": "Example Industries",
    "idea_reference": "IDEA-2026-0001",
    "idea_title": "Reduce changeover <b>waiting</b> time",
    "submitter_name": "Umang Prajapati",
    "problem_statement": "Manual checks slow every batch.",
    "estimated_saving": "₹1,00,000",
    "action_url": "https://example.transpire.test/t/example/ideas/1?section=approval",
    "stage_name": "Head of department",
}
CASES = {
    "approval_request": {
        **IDEA,
        **PREFS,
        "due": "20 Nov 2026, 10:00 UTC",
        "action_label": "Review and decide",
    },
    "approval_withdrawn": {
        **IDEA,
        **PREFS,
        "reason": "HoD changed in the HR file.",
        "action_label": "View idea",
    },
    "idea_needs_correction": {
        **IDEA,
        **PREFS,
        "approver_name": "Ashutosh Patel",
        "comment": "Add the batch data.\nThanks",
        "action_label": "Correct your idea",
    },
    "idea_rejected": {
        **IDEA,
        **PREFS,
        "approver_name": "Ashutosh Patel",
        "comment": "Not feasible <now>.",
        "action_label": "View your idea",
    },
    "comment_request": {
        **IDEA,
        **PREFS,
        "approver_names": "Ashutosh Patel",
        "action_label": "Read and comment",
    },
    "comment_posted": {
        **IDEA,
        **PREFS,
        "author_name": "Oscar Excellence",
        "comment": "Unit 4 tried this <script>",
        "is_reply": "",
        "action_label": "Read and reply",
    },
    "approval_overdue": {
        **IDEA,
        **PREFS,
        "overdue_by": "2 days",
        "due": "18 Nov 2026, 10:00 UTC",
        "reminder_number": "3",
        "final_reminder": "yes",
        "action_label": "Review and decide",
    },
    "approval_escalation": {
        **IDEA,
        **PREFS,
        "overdue_by": "3 days",
        "due": "18 Nov 2026, 10:00 UTC",
        "reminder_number": "3",
        "final_reminder": "yes",
        "approver_name": "Hema Rao",
        "relation": "reporting manager",
        "action_label": "View the idea",
    },
    "role_changed": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "previous_role": "Contributor",
        "new_role": "Workspace Admin",
        "changed_by": "Jordan Lee",
        "role_meaning": "You can manage configuration.",
        "action_url": "https://example.transpire.test/t/example/home",
        "action_label": "Open TRANSPIRE",
    },
    "privileged_role_granted": {
        "recipient_name": "Avery <script>",
        "tenant_name": "Example Industries",
        "previous_role": "Contributor",
        "new_role": "Workspace Owner",
        "changed_by": "Jordan Lee",
        "member_name": "Sam <Lee>",
        "member_email": "sam@example.com",
        "action_url": "https://example.transpire.test/t/example/admin/people",
        "action_label": "Review people",
    },
}


@pytest.mark.parametrize(("template_key", "data"), CASES.items())
def test_review_templates_render_safely(template_key: str, data: dict[str, str]) -> None:
    rendered = EmailTemplateRenderer().render(
        EmailMessage(
            tenant_id=uuid.uuid4(),
            recipient="avery@example.com",
            template_key=template_key,
            subject="TRANSPIRE",
            template_data=data,
        )
    )
    assert "<script>" not in rendered.html_body
    assert data["action_url"] in rendered.html_body and data["action_url"] in rendered.text_body
    assert data["action_label"] in rendered.html_body
    assert "Hi Avery" in rendered.text_body
    if "secondary_url" in data:
        assert "Manage preferences" in rendered.html_body
    else:
        # Security notices cannot be switched off, so they never offer preferences.
        assert "Manage preferences" not in rendered.html_body
    for value in ("comment", "reason", "due", "new_role"):
        if value in data and "<" not in data[value]:
            assert data[value].split("\n")[0] in rendered.text_body
