import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domains.projects.schemas import ProjectCharterSnapshotRecord, ProjectMilestonePlanCommand
from app.main import app


def test_project_workspace_route_and_sections_are_published() -> None:
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get("/openapi.json")

    document = response.json()
    assert "/api/v1/projects/{project_id}" in document["paths"]
    assert "put" in document["paths"]["/api/v1/projects/{project_id}/milestones"]
    workspace = document["components"]["schemas"]["ProjectWorkspaceRecord"]
    assert {
        "charter",
        "benefit_periods",
        "milestones",
        "team",
        "baselines",
        "activity",
    }.issubset(workspace["required"])


def test_migrated_baseline_snapshot_receives_safe_collection_defaults() -> None:
    snapshot = ProjectCharterSnapshotRecord.model_validate(
        {"leader": "Project Lead", "objective": "Reduce cycle time."}
    )

    assert snapshot.team_members == []
    assert snapshot.impact_areas == []
    assert snapshot.action_items == []


def test_milestone_plan_rejects_excess_weight_and_unknown_dependencies() -> None:
    with pytest.raises(ValidationError, match="cannot total more than 100"):
        ProjectMilestonePlanCommand.model_validate(
            {"milestones": [
                {"position": 1, "title": "First", "weight": 60, "progress": 0},
                {"position": 2, "title": "Second", "weight": 60, "progress": 0},
            ]}
        )

    with pytest.raises(ValidationError, match="dependencies must reference"):
        ProjectMilestonePlanCommand.model_validate(
            {
                "milestones": [
                    {
                        "position": 1,
                        "title": "First",
                        "weight": 50,
                        "progress": 0,
                        "dependency_ids": ["00000000-0000-0000-0000-000000000001"],
                    }
                ]
            }
        )
