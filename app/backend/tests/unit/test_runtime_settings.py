import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backend.db.base import Base
from app.backend.schemas.settings import RuntimeSettingsUpdate
from app.backend.services.runtime_settings import (
    get_runtime_settings,
    invalidate_boolean_settings_cache,
    upsert_runtime_settings,
)

os.environ.setdefault("INGESTION_MODEL_NAME", "")
os.environ.setdefault("LOCAL_AGENT_MODEL_NAME", "")
os.environ.setdefault("REASONING_MODEL_NAME", "")


@pytest_asyncio.fixture
async def engine():
    return create_async_engine("sqlite+aiosqlite:///:memory:", future=True)


@pytest_asyncio.fixture
async def session_factory(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_get_settings_returns_defaults_when_db_empty(session_factory) -> None:
    invalidate_boolean_settings_cache()
    async with session_factory() as session:
        settings = await get_runtime_settings(session)
        assert settings.enable_auto_carrier_search is False
        assert settings.enable_ingestion_smart_comms_handoff is False
        assert settings.enable_smart_comms_retrieval is False
        assert settings.enable_carrier_search_retrieval is False


@pytest.mark.asyncio
async def test_partial_update_persists_and_merges(session_factory) -> None:
    invalidate_boolean_settings_cache()
    async with session_factory() as session:
        updated = await upsert_runtime_settings(
            session, RuntimeSettingsUpdate(enable_auto_carrier_search=True)
        )
        await session.commit()

        assert updated.enable_auto_carrier_search is True
        assert updated.enable_ingestion_smart_comms_handoff is False

    async with session_factory() as session:
        reloaded = await get_runtime_settings(session)
        assert reloaded.enable_auto_carrier_search is True
        assert reloaded.enable_ingestion_smart_comms_handoff is False


@pytest.mark.asyncio
async def test_full_update_roundtrip(session_factory) -> None:
    invalidate_boolean_settings_cache()
    async with session_factory() as session:
        await upsert_runtime_settings(
            session,
            RuntimeSettingsUpdate(
                enable_auto_carrier_search=True,
                enable_ingestion_smart_comms_handoff=True,
                enable_smart_comms_retrieval=False,
                enable_carrier_search_retrieval=False,
            ),
        )
        await session.commit()

    async with session_factory() as session:
        settings = await get_runtime_settings(session)
        assert settings.enable_auto_carrier_search is True
        assert settings.enable_ingestion_smart_comms_handoff is True
        assert settings.enable_smart_comms_retrieval is False
        assert settings.enable_carrier_search_retrieval is False


@pytest.mark.asyncio
async def test_empty_update_does_not_overwrite(session_factory) -> None:
    invalidate_boolean_settings_cache()
    async with session_factory() as session:
        await upsert_runtime_settings(
            session,
            RuntimeSettingsUpdate(enable_auto_carrier_search=True),
        )
        await session.commit()

        await upsert_runtime_settings(session, RuntimeSettingsUpdate())
        await session.commit()

        settings = await get_runtime_settings(session)
        assert settings.enable_auto_carrier_search is True
