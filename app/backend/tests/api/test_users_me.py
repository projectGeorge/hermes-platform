import pytest
from httpx import AsyncClient

from app.backend.core.clerk_auth import ClerkUserProfile


@pytest.mark.asyncio
async def test_get_current_user_provisions_and_returns_operator(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_profile(_: str, *, secret_key: str | None, api_url: str = "https://api.clerk.com/v1") -> ClerkUserProfile:
        assert secret_key is None or isinstance(secret_key, str)
        assert api_url == "https://api.clerk.com/v1"
        return ClerkUserProfile(
            auth_id="user_live_123",
            email="operator.frontend@example.com",
            operator_name="Frontend Operator",
        )

    monkeypatch.setattr(
        "app.backend.api.dependencies.auth.fetch_clerk_user_profile",
        fake_profile,
    )
    monkeypatch.setattr(
        "app.backend.api.dependencies.auth.verify_clerk_token",
        lambda token, jwt_key, authorized_parties: type(
            "Claims",
            (),
            {"auth_id": "user_live_123", "session_id": "sess_live_123"},
        )(),
    )

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["auth_id"] == "user_live_123"
    assert response.json()["email"] == "operator.frontend@example.com"
    assert response.json()["operator_name"] == "Frontend Operator"


@pytest.mark.asyncio
async def test_get_current_user_reuses_locally_provisioned_operator_without_clerk_roundtrip(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.backend.api.dependencies.auth.verify_clerk_token",
        lambda token, jwt_key, authorized_parties: type(
            "Claims",
            (),
            {"auth_id": "auth_demo", "session_id": "sess_demo_123"},
        )(),
    )

    async def fail_if_called(_: str, *, secret_key: str | None, api_url: str = "https://api.clerk.com/v1") -> ClerkUserProfile:
        raise AssertionError("fetch_clerk_user_profile should not be called for an existing local user")

    monkeypatch.setattr(
        "app.backend.api.dependencies.auth.fetch_clerk_user_profile",
        fail_if_called,
    )

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["auth_id"] == "auth_demo"
    assert response.json()["email"] == "operator@example.com"
    assert response.json()["operator_name"] == "Operator Demo"
