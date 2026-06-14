import pytest
from fastapi import HTTPException

from app.backend.core import clerk_auth


def test_extract_bearer_token_returns_token_value() -> None:
    assert clerk_auth.extract_bearer_token("Bearer token-value") == "token-value"


def test_extract_bearer_token_rejects_missing_header() -> None:
    with pytest.raises(HTTPException) as exc_info:
        clerk_auth.extract_bearer_token(None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing bearer token"


def test_verify_clerk_token_accepts_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        clerk_auth.jwt,
        "decode",
        lambda token, key, algorithms, options: {
            "sub": "user_test_123",
            "sid": "sess_test_123",
            "azp": "http://localhost:5173",
        },
    )

    claims = clerk_auth.verify_clerk_token(
        "signed-token",
        jwt_key="public-key",
        authorized_parties=["http://localhost:5173"],
    )

    assert claims.auth_id == "user_test_123"
    assert claims.session_id == "sess_test_123"


def test_verify_clerk_token_rejects_invalid_authorized_party(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        clerk_auth.jwt,
        "decode",
        lambda token, key, algorithms, options: {
            "sub": "user_test_123",
            "sid": "sess_test_123",
            "azp": "http://malicious.local",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        clerk_auth.verify_clerk_token(
            "signed-token",
            jwt_key="public-key",
            authorized_parties=["http://localhost:5173"],
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid authorized party"
