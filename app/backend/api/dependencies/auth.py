"""Authentication dependencies for FastAPI endpoints."""

from typing import Annotated

from fastapi import Depends, Request

from app.backend.core.clerk_auth import (
    extract_bearer_token,
    fetch_clerk_user_profile,
    verify_clerk_token,
)
from app.backend.core.settings import get_settings
from app.backend.db.session import AsyncSessionDep
from app.backend.models.user import User
from app.backend.services.current_user import (
    get_current_user_by_auth_id,
    get_or_provision_current_user,
)


async def get_current_user(request: Request, session: AsyncSessionDep) -> User:
    """Resolve the current Hermes operator from the Clerk bearer token."""

    settings = get_settings()
    token = extract_bearer_token(request.headers.get("Authorization"))
    claims = verify_clerk_token(
        token,
        jwt_key=settings.clerk_jwt_key,
        authorized_parties=settings.clerk_authorized_parties,
    )
    existing_user = await get_current_user_by_auth_id(session, claims.auth_id)
    if existing_user is not None:
        return existing_user

    profile = await fetch_clerk_user_profile(
        claims.auth_id,
        secret_key=settings.clerk_secret_key,
    )
    user = await get_or_provision_current_user(session, profile)
    await session.commit()
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
