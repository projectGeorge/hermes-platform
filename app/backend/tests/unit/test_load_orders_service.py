from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backend.models.truck_type import TruckType
from app.backend.core.domain_enums import LoadOrderStatus
from app.backend.db.base import Base
from app.backend.models.ingestion_run import IngestionRun
from app.backend.models.load_order_human_review import LoadOrderHumanReview
from app.backend.models.load_order import LoadOrder
from app.backend.models.user import User
from app.backend.schemas.load_order import LoadOrderCreate, LoadOrderUpdate
from app.backend.services.load_orders import (
    create_load_order,
    delete_load_order,
    get_load_order_by_id,
    get_load_order_or_404,
    update_load_order,
    validate_formalization_transition,
    validate_load_order_payload,
)
from app.backend.core.domain_enums import IngestionRunStatus, LoadOrderHumanReviewStatus


def test_validate_load_order_payload_rejects_unordered_schedule() -> None:
    payload = LoadOrderCreate(
        user_id="7d0f9c46-90e8-4dcb-b1b0-9190459138c8",
        origin_load_date=datetime(2026, 4, 11, 10, 0, 0),
        destination_unload_date=datetime(2026, 4, 10, 10, 0, 0),
    )

    with pytest.raises(ValueError):
        validate_load_order_payload(payload)


def test_validate_formalization_transition_requires_valid_status() -> None:
    with pytest.raises(ValueError):
        validate_formalization_transition(LoadOrderStatus.VIABILITY_PENDING)


@pytest.mark.asyncio
async def test_create_load_order_delegates_to_runtime_service() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    user = User(
        id=uuid4(),
        email="operator@example.com",
        operator_name="Operator Demo",
        auth_id="auth_demo",
    )

    async with session_factory() as session:
        session.add(user)
        await session.commit()

    payload = LoadOrderCreate(user_id=user.id)

    async with session_factory() as session:
        created_order = await create_load_order(session, payload)
        await session.commit()
        loaded_order = await get_load_order_by_id(session, created_order.id)

    assert created_order.id == loaded_order.id
    assert created_order.user_id == user.id
    assert created_order.status == LoadOrderStatus.PENDING_INGESTION

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_load_order_translates_invalid_schedule_error() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    user = User(
        id=uuid4(),
        email="operator@example.com",
        operator_name="Operator Demo",
        auth_id="auth_demo",
    )

    async with session_factory() as session:
        session.add(user)
        await session.commit()

    payload = LoadOrderCreate(
        user_id=user.id,
        origin_load_date=datetime(2026, 4, 11, 10, 0, 0),
        destination_unload_date=datetime(2026, 4, 10, 10, 0, 0),
    )

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await create_load_order(session, payload)

    assert exc_info.value.status_code == 422
    assert (
        exc_info.value.detail
        == "destination_unload_date cannot be earlier than origin_load_date"
    )

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_load_order_seeds_canonical_truck_type_before_write() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    user = User(
        id=uuid4(),
        email="operator@example.com",
        operator_name="Operator Demo",
        auth_id="auth_demo",
    )

    async with session_factory() as session:
        session.add(user)
        await session.commit()

    payload = LoadOrderCreate(user_id=user.id, truck_type_id=1)

    async with session_factory() as session:
        created_order = await create_load_order(session, payload)
        await session.commit()
        truck_types = list((await session.execute(select(TruckType).order_by(TruckType.id))).scalars())

    assert created_order.truck_type_id == 1
    assert [(truck_type.id, truck_type.name) for truck_type in truck_types] == [
        (1, "tautliner"),
        (2, "reefer"),
        (3, "mega"),
    ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_load_order_seeds_canonical_truck_type_before_write() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    user = User(
        id=uuid4(),
        email="operator@example.com",
        operator_name="Operator Demo",
        auth_id="auth_demo",
    )

    async with session_factory() as session:
        session.add(user)
        await session.commit()

    async with session_factory() as session:
        created_order = await create_load_order(session, LoadOrderCreate(user_id=user.id))
        await session.commit()

    async with session_factory() as session:
        updated_order = await update_load_order(
            session,
            created_order.id,
            LoadOrderUpdate(truck_type_id=2),
        )
        await session.commit()
        truck_types = list((await session.execute(select(TruckType).order_by(TruckType.id))).scalars())

    assert updated_order.truck_type_id == 2
    assert [(truck_type.id, truck_type.name) for truck_type in truck_types] == [
        (1, "tautliner"),
        (2, "reefer"),
        (3, "mega"),
    ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_load_order_or_404_translates_not_found_detail() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await get_load_order_or_404(session, uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Load order not found"

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_load_order_translates_not_found_detail() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await update_load_order(session, uuid4(), LoadOrderUpdate())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Load order not found"

    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_load_order_deletes_human_reviews_before_ingestion_runs() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    user_id = uuid4()
    order_id = uuid4()

    async with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email="operator@example.com",
                operator_name="Operator Demo",
                auth_id="auth_demo",
            )
        )
        session.add(
            LoadOrder(
                id=order_id,
                user_id=user_id,
                status=LoadOrderStatus.PENDING_INGESTION,
                currency="EUR",
            )
        )

        ingestion_run = IngestionRun(
            user_id=user_id,
            route="load_order_ingestion",
            status=IngestionRunStatus.COMPLETED,
            raw_text="raw",
            load_order_id=order_id,
        )
        session.add(ingestion_run)
        await session.flush()

        session.add(
            LoadOrderHumanReview(
                load_order_id=order_id,
                ingestion_run_id=ingestion_run.id,
                reviewed_by_user_id=user_id,
                review_status=LoadOrderHumanReviewStatus.FIELDS_UPDATED,
                submitted_fields={"cargo_description": "Tiles"},
                remaining_missing_fields={},
                review_notes=None,
            )
        )
        await session.commit()

    async with session_factory() as session:
        await delete_load_order(session, order_id)
        await session.commit()

    async with session_factory() as session:
        assert await session.get(LoadOrder, order_id) is None
        reviews = (await session.execute(select(LoadOrderHumanReview))).scalars().all()
        runs = (await session.execute(select(IngestionRun))).scalars().all()
        assert reviews == []
        assert runs == []

    await engine.dispose()
