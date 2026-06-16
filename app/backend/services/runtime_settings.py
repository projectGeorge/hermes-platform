from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.settings import get_settings
from app.backend.models.app_runtime_setting import AppRuntimeSetting
from app.backend.schemas.settings import RuntimeSettingsResponse, RuntimeSettingsUpdate

_RUNTIME_DEFAULTS: dict[str, object] = {
    "enable_auto_carrier_search": False,
    "enable_ingestion_smart_comms_handoff": False,
    "enable_smart_comms_retrieval": False,
    "enable_carrier_search_retrieval": False,
}

_BOOLEAN_KEYS = frozenset(_RUNTIME_DEFAULTS.keys())


def _build_response(stored: dict[str, object] | None) -> RuntimeSettingsResponse:
    env = get_settings()
    merged = dict(_RUNTIME_DEFAULTS)
    if stored:
        merged.update(stored)

    try:
        from app.backend.services.chroma_runtime import check_health_cached
        chroma_reachable = check_health_cached()
    except Exception:
        chroma_reachable = False

    return RuntimeSettingsResponse(
        enable_auto_carrier_search=bool(merged.get("enable_auto_carrier_search", False)),
        enable_ingestion_smart_comms_handoff=bool(merged.get("enable_ingestion_smart_comms_handoff", False)),
        enable_smart_comms_retrieval=bool(merged.get("enable_smart_comms_retrieval", False)),
        enable_carrier_search_retrieval=bool(merged.get("enable_carrier_search_retrieval", False)),
        ingestion_provider=env.ingestion_model_provider,
        ingestion_model_name=env.ingestion_model_name,
        reasoning_provider=env.reasoning_model_provider,
        reasoning_model_name=env.reasoning_model_name,
        chroma_reachable=chroma_reachable,
    )


async def get_runtime_settings(session: AsyncSession, user_id: UUID) -> RuntimeSettingsResponse:
    from sqlalchemy import select
    from app.backend.models.app_runtime_setting import AppRuntimeSetting
    
    stmt = select(AppRuntimeSetting).where(
        (AppRuntimeSetting.key == "runtime_settings"),
        (AppRuntimeSetting.user_id == user_id)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    stored = row.value_json if row else None
    return _build_response(stored)


async def upsert_runtime_settings(
    session: AsyncSession,
    payload: RuntimeSettingsUpdate,
    user_id: UUID,
) -> RuntimeSettingsResponse:
    from sqlalchemy import select
    from app.backend.models.app_runtime_setting import AppRuntimeSetting
    
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return await get_runtime_settings(session, user_id)

    stmt = select(AppRuntimeSetting).where(
        (AppRuntimeSetting.key == "runtime_settings"),
        (AppRuntimeSetting.user_id == user_id)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    
    if row is None:
        row = AppRuntimeSetting(
            key="runtime_settings", 
            user_id=user_id,
            value_json=dict(_RUNTIME_DEFAULTS)
        )
        session.add(row)

    row.value_json = {**row.value_json, **updates}
    await session.flush()
    return await get_runtime_settings(session, user_id)


_BOOLEAN_SETTINGS_CACHE: dict[str, bool] | None = None


async def load_boolean_settings(session: AsyncSession) -> dict[str, bool]:
    global _BOOLEAN_SETTINGS_CACHE
    if _BOOLEAN_SETTINGS_CACHE is not None:
        return _BOOLEAN_SETTINGS_CACHE

    settings = await get_runtime_settings(session)
    _BOOLEAN_SETTINGS_CACHE = {
        "enable_auto_carrier_search": settings.enable_auto_carrier_search,
        "enable_ingestion_smart_comms_handoff": settings.enable_ingestion_smart_comms_handoff,
        "enable_smart_comms_retrieval": settings.enable_smart_comms_retrieval,
        "enable_carrier_search_retrieval": settings.enable_carrier_search_retrieval,
    }
    return _BOOLEAN_SETTINGS_CACHE


def invalidate_boolean_settings_cache() -> None:
    global _BOOLEAN_SETTINGS_CACHE
    _BOOLEAN_SETTINGS_CACHE = None
