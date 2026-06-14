from fastapi import APIRouter, Depends

from app.backend.api.dependencies.auth import CurrentUserDep, get_current_user
from app.backend.db.session import AsyncSessionDep
from app.backend.schemas.settings import RuntimeSettingsResponse, RuntimeSettingsUpdate
from app.backend.services.runtime_settings import (
    get_runtime_settings,
    invalidate_boolean_settings_cache,
    upsert_runtime_settings,
)

router = APIRouter(
    prefix="/settings",
    tags=["Settings"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/runtime", response_model=RuntimeSettingsResponse)
async def get_runtime_settings_endpoint(
    session: AsyncSessionDep,
) -> RuntimeSettingsResponse:
    return await get_runtime_settings(session)


@router.put("/runtime", response_model=RuntimeSettingsResponse)
async def update_runtime_settings_endpoint(
    payload: RuntimeSettingsUpdate,
    session: AsyncSessionDep,
) -> RuntimeSettingsResponse:
    result = await upsert_runtime_settings(session, payload)
    invalidate_boolean_settings_cache()
    await session.commit()
    return result
