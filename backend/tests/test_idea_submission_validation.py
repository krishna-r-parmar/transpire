import uuid

import pytest

from app.domains.ideas.controllers import IdeaValidationError, _validate_required_submission
from app.domains.ideas.schemas import IdeaUpsertCommand


def submission_command(**overrides: object) -> IdeaUpsertCommand:
    values = {
        "category_id": uuid.uuid4(),
        "subcategory_id": uuid.uuid4(),
        "title": "Reduce tooling wait time",
        "problem_statement": "Operators wait for verified tooling during changeovers.",
        "business_case": "Preparing tooling earlier will reduce avoidable downtime.",
        "impacts": ["delivery"],
    }
    values.update(overrides)
    return IdeaUpsertCommand.model_validate(values)


def test_submission_does_not_require_process_area() -> None:
    command = submission_command(process_area_id=None)

    _validate_required_submission(command)


def test_submission_still_requires_current_required_fields() -> None:
    command = submission_command(title="")

    with pytest.raises(IdeaValidationError, match="required fields: title"):
        _validate_required_submission(command)
