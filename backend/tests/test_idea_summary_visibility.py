import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domains.ideas.controllers import (
    BANK_STATUSES,
    JOINABLE_STATUSES,
    BankVisibility,
    bank_entry_fields,
    can_manage_idea,
    join_state_for,
)
from app.domains.ideas.models import IdeaBankPolicy, IdeaStatus
from app.domains.ideas.schemas import IdeaSummaryRecord

OWNER = uuid.uuid4()
APPROVER = uuid.uuid4()
COLLEAGUE = uuid.uuid4()


def _idea(status: IdeaStatus = IdeaStatus.APPROVED) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        reference="IDEA-2026-0001",
        title="Pre-heat boiler feed water",
        status=status,
        idea_type="project",
        submitted_at=datetime(2026, 10, 23, tzinfo=UTC),
        submitter_user_id=OWNER,
        impacts=["cost"],
        current_state="84",
        baseline_uom="units",
        target_state="34",
        target_uom="units",
        problem_statement="Cold feed water wastes fuel.",
        business_case="Solar pre-heating cuts fuel use.",
        estimated_annual_saving=Decimal(1850000),
        cost_avoidance=Decimal(40000),
        investment_required=Decimal(900000),
        usd_exchange_rate=Decimal("0.0106"),
        fx_rate_date=date(2026, 11, 17),
    )


def _fields(visibility: BankVisibility) -> dict:
    return bank_entry_fields(_idea(), "Asha Rao", "OPEX", "OEE", "Distillation", visibility)


def _policy(detail_level: str, *, contributor: bool, financials: bool) -> IdeaBankPolicy:
    return IdeaBankPolicy(
        tenant_id=uuid.uuid4(),
        detail_level=detail_level,
        show_contributor=contributor,
        show_financials=financials,
    )


def test_summary_policy_hides_everything_beyond_the_basic_record() -> None:
    fields = _fields(
        BankVisibility.from_policy(_policy("basic", contributor=False, financials=False))
    )

    assert fields["title"] == "Pre-heat boiler feed water"
    assert fields["category"] == "OPEX"
    # People are always visible so colleagues can find and join improvements.
    assert fields["contributor"] == "Asha Rao"
    for hidden in (
        "subcategory",
        "impacts",
        "current_state",
        "problem_statement",
        "business_case",
        "estimated_annual_saving",
        "estimated_annual_saving_usd",
        "investment_required",
        "usd_exchange_rate",
    ):
        assert fields[hidden] is None, hidden


def test_operational_policy_shows_classification_but_not_the_narrative() -> None:
    fields = _fields(
        BankVisibility.from_policy(_policy("operational", contributor=True, financials=False))
    )

    assert fields["contributor"] == "Asha Rao"
    assert fields["subcategory"] == "OEE"
    assert fields["current_state"] == "84"
    assert fields["problem_statement"] is None
    assert fields["estimated_annual_saving"] is None


def test_full_policy_with_financials_shows_the_value_case() -> None:
    fields = _fields(BankVisibility.from_policy(_policy("full", contributor=True, financials=True)))

    assert fields["business_case"] == "Solar pre-heating cuts fuel use."
    assert fields["estimated_annual_saving"] == Decimal(1850000)
    assert fields["estimated_annual_saving_usd"] is not None


def test_summary_record_accepts_policy_filtered_fields() -> None:
    record = IdeaSummaryRecord(
        **_fields(
            BankVisibility.from_policy(_policy("basic", contributor=False, financials=False))
        ),
        shows_operational=False,
    )

    assert record.contributor == "Asha Rao" and record.can_manage is False
    assert record.join_state == "closed" and record.team == []


@pytest.mark.parametrize(
    ("user_id", "roles", "expected"),
    [
        (OWNER, ["idea_submitter"], True),
        (APPROVER, ["idea_submitter"], True),
        (COLLEAGUE, ["tenant_admin"], True),
        (COLLEAGUE, ["workspace_owner"], True),
        (COLLEAGUE, ["idea_submitter"], False),
        (COLLEAGUE, ["viewer"], False),
    ],
)
def test_only_owner_approvers_and_admins_manage_an_idea(
    user_id: uuid.UUID, roles: list[str], expected: bool
) -> None:
    stages = [SimpleNamespace(assignee_user_id=APPROVER)]

    assert can_manage_idea(_idea(), stages, user_id, roles) is expected


def test_private_statuses_never_reach_the_idea_bank() -> None:
    for private in (
        IdeaStatus.DRAFT,
        IdeaStatus.NEEDS_CORRECTION,
        IdeaStatus.REJECTED,
        IdeaStatus.WITHDRAWN,
    ):
        assert private not in BANK_STATUSES


def _state(**overrides: bool) -> str:
    facts = {
        "is_owner": False,
        "is_member": False,
        "has_pending": False,
        "joinable": True,
        "may_contribute": True,
    }
    facts.update(overrides)
    return join_state_for(**facts)


def test_contributors_can_ask_to_join_an_approved_idea() -> None:
    assert _state() == "available"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"is_owner": True}, "owner"),
        ({"is_member": True}, "member"),
        ({"has_pending": True}, "pending"),
        ({"joinable": False}, "closed"),
        ({"may_contribute": False}, "not_allowed"),
        # Owners and existing members are never asked to join, even before approval.
        ({"is_owner": True, "joinable": False}, "owner"),
        ({"is_member": True, "may_contribute": False}, "member"),
    ],
)
def test_join_state_explains_why_someone_cannot_ask(overrides: dict, expected: str) -> None:
    assert _state(**overrides) == expected


def test_only_approved_ideas_take_join_requests() -> None:
    assert JOINABLE_STATUSES == {
        IdeaStatus.APPROVED,
        IdeaStatus.CHARTER_IN_PROGRESS,
        IdeaStatus.CHARTER_SUBMITTED,
    }
