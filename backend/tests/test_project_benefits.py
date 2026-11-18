from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.domains.projects.controllers import (
    add_months,
    annual_target_lakhs,
    benefit_totals,
    monthly_plan,
)


def test_annual_target_is_saving_plus_avoidance_in_lakhs() -> None:
    idea = SimpleNamespace(estimated_annual_saving=Decimal(1850000), cost_avoidance=Decimal(40000))

    assert annual_target_lakhs(idea) == Decimal("18.90")


def test_kpi_only_ideas_have_no_money_target() -> None:
    idea = SimpleNamespace(estimated_annual_saving=None, cost_avoidance=None)

    assert annual_target_lakhs(idea) == Decimal("0.00")


def test_monthly_plan_spreads_the_target_and_keeps_the_total() -> None:
    plan = monthly_plan(Decimal("18.90"))

    assert len(plan) == 12
    assert plan[0] == Decimal("1.58")
    assert sum(plan) == Decimal("18.90")


def test_months_roll_over_the_year() -> None:
    assert add_months(date(2027, 2, 1), 0) == date(2027, 2, 1)
    assert add_months(date(2027, 2, 1), 11) == date(2028, 1, 1)
    assert add_months(date(2026, 11, 1), 2) == date(2027, 1, 1)


def test_only_validated_months_count_as_validated() -> None:
    months = [
        SimpleNamespace(
            actual=Decimal("1.50"), line_of_sight=Decimal("0.20"), finance_status="validated"
        ),
        SimpleNamespace(actual=Decimal("1.00"), line_of_sight=None, finance_status="submitted"),
        SimpleNamespace(actual=None, line_of_sight=Decimal("1.00"), finance_status="open"),
    ]

    assert benefit_totals(months) == (Decimal("2.50"), Decimal("1.50"), Decimal("1.20"))
