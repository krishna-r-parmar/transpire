from app.domains.identity.services import generate_session_token
from app.domains.identity.sso import tenant_slug_from_state


def test_tenant_slug_is_read_from_state() -> None:
    assert tenant_slug_from_state(f"erc-group.{generate_session_token()}") == "erc-group"


def test_legacy_state_without_tenant_has_no_slug() -> None:
    assert tenant_slug_from_state(generate_session_token()) is None


def test_malformed_state_has_no_slug() -> None:
    assert tenant_slug_from_state(".token") is None
    assert tenant_slug_from_state("erc-group.") is None


def test_global_callback_hands_tenant_states_to_tenant_flow(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.responses import RedirectResponse
    from fastapi.testclient import TestClient

    from app.core.database import get_session
    from app.domains.identity import sso_views

    received: dict[str, str] = {}

    async def fake_tenant_callback(request, settings, session, code, state_token):
        received["state"] = state_token
        return RedirectResponse("http://app.test/t/erc-group/", status_code=303)

    async def fake_global(**_):
        raise AssertionError("tenant state must not reach the shared workspace flow")

    async def no_session():
        yield None

    monkeypatch.setattr(sso_views, "sso_callback", fake_tenant_callback)
    monkeypatch.setattr(sso_views, "complete_global_sso", fake_global)
    application = FastAPI()
    application.include_router(sso_views.router, prefix="/api/v1")
    application.dependency_overrides[get_session] = no_session

    state = f"erc-group.{generate_session_token()}"
    response = TestClient(application).get(
        "/api/v1/auth/sso/global/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert received["state"] == state
