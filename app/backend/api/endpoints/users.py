from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select

from app.backend.api.dependencies.auth import CurrentUserDep
from app.backend.db.session import AsyncSessionDep
from app.backend.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    operator_name: str
    auth_id: str


class UserCreate(BaseModel):
    email: EmailStr
    operator_name: str
    auth_id: str


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        operator_name=user.operator_name,
        auth_id=user.auth_id,
    )


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, session: AsyncSessionDep) -> UserResponse:
    new_user = User(
        email=str(payload.email),
        operator_name=payload.operator_name,
        auth_id=payload.auth_id,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return _to_user_response(new_user)


@router.get("/", response_model=list[UserResponse])
async def list_users(
    session: AsyncSessionDep,
    skip: int = 0,
    limit: int = 100,
) -> list[UserResponse]:
    stmt = select(User).offset(skip).limit(limit)
    result = await session.execute(stmt)
    users = result.scalars().all()
    return [_to_user_response(user) for user in users]


@router.get("/me", response_model=UserResponse)
async def get_current_user_endpoint(
    current_user: CurrentUserDep,
) -> UserResponse:
    return _to_user_response(current_user)
