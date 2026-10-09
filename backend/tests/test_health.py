from fastapi.testclient import TestClient

from app.main import app


def test_liveness() -> None:
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_is_versioned() -> None:
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/ideas" in response.json()["paths"]
