"""Services for resolving the authenticated Hermes operator."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.clerk_auth import ClerkUserProfile
from app.backend.models.user import User


async def get_current_user_by_auth_id(
    session: AsyncSession,
    auth_id: str,
) -> User | None:
    """Return the local user for a Clerk auth_id if already provisioned."""

    result = await session.execute(select(User).where(User.auth_id == auth_id))
    return result.scalar_one_or_none()


async def get_or_provision_current_user(
    session: AsyncSession,
    profile: ClerkUserProfile,
) -> User:
    """Return the local user for a Clerk identity, creating it if needed."""

    user = await get_current_user_by_auth_id(session, profile.auth_id)
    if user is not None:
        return user

    # Fallback: search by email in case auth_id changed (e.g., account recreated in Clerk)
    result = await session.execute(select(User).where(User.email == str(profile.email)))
    user = result.scalar_one_or_none()
    if user is not None:
        # Update auth_id to the new one from Clerk
        user.auth_id = profile.auth_id
        await session.flush()
        return user

    user = User(
        email=str(profile.email),
        operator_name=profile.operator_name,
        auth_id=profile.auth_id,
    )
    session.add(user)
    await session.flush()
    return user
