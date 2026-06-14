"""Helpers for Clerk token verification and profile loading."""

from typing import Any

import httpx
import jwt
from fastapi import HTTPException, status
from pydantic import BaseModel, EmailStr


class VerifiedClerkToken(BaseModel):
    """Verified claims required by Hermes."""

    auth_id: str
    session_id: str | None = None


class ClerkUserProfile(BaseModel):
    """Minimal Clerk user profile used for local provisioning."""

    auth_id: str
    email: EmailStr
    operator_name: str


def extract_bearer_token(header_value: str | None) -> str:
    """Extract the bearer token from an Authorization header."""

    if header_value is None or not header_value.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    return header_value.removeprefix("Bearer ").strip()


def verify_clerk_token(
    token: str,
    *,
    jwt_key: str | None,
    authorized_parties: list[str],
) -> VerifiedClerkToken:
    """Verify a Clerk session token using the configured public key."""

    if not jwt_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLERK_JWT_KEY is not configured",
        )

    try:
        payload = jwt.decode(
            token,
            jwt_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc

    azp = payload.get("azp")
    if azp is not None and azp not in authorized_parties:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorized party",
        )

    return VerifiedClerkToken(
        auth_id=payload["sub"],
        session_id=payload.get("sid"),
    )


def _extract_primary_email(payload: dict[str, Any]) -> str:
    primary_email_address_id = payload.get("primary_email_address_id")
    for email_item in payload.get("email_addresses", []):
        if email_item.get("id") == primary_email_address_id:
            return email_item["email_address"]

    email_addresses = payload.get("email_addresses", [])
    if email_addresses:
        return email_addresses[0]["email_address"]

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Clerk user is missing a primary email",
    )


def _extract_operator_name(payload: dict[str, Any]) -> str:
    first_name = payload.get("first_name")
    last_name = payload.get("last_name")
    display_name = " ".join(part for part in [first_name, last_name] if part)
    return display_name or payload.get("username") or "Hermes Operator"


async def fetch_clerk_user_profile(
    auth_id: str,
    *,
    secret_key: str | None,
    api_url: str = "https://api.clerk.com/v1",
) -> ClerkUserProfile:
    """Fetch the Clerk profile used to provision the local Hermes operator."""

    if not secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLERK_SECRET_KEY is not configured",
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{api_url}/users/{auth_id}",
            headers={"Authorization": f"Bearer {secret_key}"},
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk user not found",
        )
    response.raise_for_status()

    payload = response.json()
    return ClerkUserProfile(
        auth_id=payload["id"],
        email=_extract_primary_email(payload),
        operator_name=_extract_operator_name(payload),
    )
