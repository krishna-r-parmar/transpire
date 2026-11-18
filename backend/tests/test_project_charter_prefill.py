import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domains.ideas.controllers import benefit_type_for, prefilled_charter
from app.domains.ideas.schemas import ProjectCharterCommand


@pytest.mark.parametrize(
    ("saving", "avoidance", "expected"),
    [
        (Decimal(1850000), Decimal(40000), "both"),
        (Decimal(1850000), None, "cost_saving"),
        (None, Decimal(40000), "cost_avoidance"),
        (Decimal(0), Decimal(0), "kpi_only"),
        (None, None, "kpi_only"),
    ],
)
def test_benefit_type_follows_the_ideas_estimates(
    saving: Decimal | None, avoidance: Decimal | None, expected: str
) -> None:
    assert benefit_type_for(saving, avoidance) == expected


def test_charter_starts_from_the_approved_idea() -> None:
    submitter = SimpleNamespace(id=uuid.uuid4(), display_name="Asha Rao")
    idea = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        department_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        target_completion_date=date(2027, 3, 31),
        impacts=["cost", "safety"],
        estimated_annual_saving=Decimal(1850000),
        cost_avoidance=None,
        investment_required=Decimal(900000),
    )

    charter = prefilled_charter(idea, leader=submitter, kpi_hint="Fuel use (units/day)")

    assert charter.leader == "Asha Rao" and charter.leader_user_id == submitter.id
    assert charter.site_id == idea.site_id and charter.department_id == idea.department_id
    assert charter.target_completion_date == date(2027, 3, 31)
    assert charter.impact_areas == ["cost", "safety"]
    assert charter.benefit_type == "cost_saving"
    assert charter.kpi_name == "Fuel use (units/day)"
    assert charter.budget_approved == Decimal(900000)
    assert charter.sponsor == "" and charter.team_members == []


def test_saving_without_delivery_fields_leaves_them_out() -> None:
    command = ProjectCharterCommand(sponsor="Vikram Kale")

    assert "action_items" not in command.model_fields_set
    assert "monthly_tracking" not in command.model_fields_set


def _milestone(title: str, due: date | None, weight: int, *, benefits: bool = False):
    from app.domains.ideas.schemas import CharterMilestone

    return CharterMilestone(
        title=title, due_date=due, weight=Decimal(weight), benefits_start=benefits
    )


def test_a_complete_plan_has_no_problems() -> None:
    from app.domains.ideas.controllers import milestone_plan_problems

    plan = [
        _milestone("Define", date(2026, 12, 15), 30),
        _milestone("Go-live", date(2027, 2, 28), 70, benefits=True),
    ]

    assert milestone_plan_problems(plan, date(2026, 12, 1), date(2027, 3, 31), "cost_saving") == []


def test_plan_problems_are_explained() -> None:
    from app.domains.ideas.controllers import milestone_plan_problems

    plan = [
        _milestone("", None, 30),
        _milestone("Late", date(2027, 6, 1), 30),
    ]

    problems = milestone_plan_problems(plan, date(2026, 12, 1), date(2027, 3, 31), "cost_saving")

    assert "Every milestone needs a title." in problems
    assert "Every milestone needs a due date." in problems
    assert any("within the charter dates (Late)" in problem for problem in problems)
    assert any("total 100% (now 60%)" in problem for problem in problems)
    assert "Mark the one milestone after which benefits start." in problems


def test_kpi_only_plans_need_no_benefit_start_but_allow_one() -> None:
    from app.domains.ideas.controllers import milestone_plan_problems

    plan = [_milestone("Trial", date(2026, 12, 15), 100)]

    assert milestone_plan_problems(plan, None, None, "kpi_only") == []
    assert milestone_plan_problems([], None, None, "kpi_only") == ["Add at least one milestone."]
