from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.backend.models  # noqa: F401
from app.backend.core.domain_enums import LoadOrderStatus, TripProposalStatus
from app.backend.db.base import Base
from app.backend.models.load_order import LoadOrder
from app.backend.models.user import User
from app.backend.schemas.load_order import LoadOrderUpdate
from app.backend.services import load_order_carrier_search as carrier_search_service
from app.backend.services.load_order_carrier_search import create_load_order_carrier_search
from app.backend.services.load_order_carrier_selection import select_load_order_carrier
from app.backend.services.load_orders import formalize_load_order, update_load_order


async def _build_session_factory() -> tuple[object, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    return engine, session_factory


async def _seed_user(session_factory: async_sessionmaker[AsyncSession]) -> User:
    user = User(
        id=uuid4(),
        email=f"operator-{uuid4()}@example.com",
        operator_name="Operator Demo",
        auth_id=f"auth_{uuid4()}",
    )

    async with session_factory() as session:
        session.add(user)
        await session.commit()

    return user


async def _seed_order(
    session_factory: async_sessionmaker[AsyncSession],
    user_id,
    *,
    status: LoadOrderStatus = LoadOrderStatus.VIABILITY_CONFIRMED,
    customer_price: Decimal = Decimal("1400.00"),
    truck_type_id: int = 1,
    adr_required: bool = False,
) -> LoadOrder:
    order = LoadOrder(
        user_id=user_id,
        status=status,
        customer_name="Acme Logistics",
        origin_text="Madrid, ES",
        destination_text="Paris, FR",
        cargo_description="Ceramic tiles",
        weight_kg=Decimal("7800.00"),
        customer_price=customer_price,
        distance_km=Decimal("1000.00"),
        truck_type_id=truck_type_id,
        adr_required=adr_required,
        currency="EUR",
        missing_fields={},
    )

    async with session_factory() as session:
        session.add(order)
        await session.commit()
        await session.refresh(order)

    return order


async def _create_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    order_id,
):
    async with session_factory() as session:
        response, created = await create_load_order_carrier_search(session, order_id)
        await session.commit()

    assert created is True
    return response


async def _seed_order_with_rejections(
    session_factory: async_sessionmaker[AsyncSession],
    user_id,
):
    order = await _seed_order(
        session_factory,
        user_id,
        customer_price=Decimal("800.00"),
        adr_required=True,
    )
    snapshot = await _create_snapshot(session_factory, order.id)
    rejected_trip_id = next(
        (
            item.trip_id
            for item in snapshot.candidates
            if item.proposal_status == TripProposalStatus.REJECTED
        ),
        None,
    )
    assert rejected_trip_id is not None
    return order, snapshot, rejected_trip_id


@pytest.mark.asyncio
async def test_select_carrier_sets_selected_trip_and_transitions_order() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)
    snapshot = await _create_snapshot(session_factory, order.id)
    selected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        response = await select_load_order_carrier(session, order.id, selected_trip_id)
        await session.commit()

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)

    assert persisted_order is not None
    assert persisted_order.status == LoadOrderStatus.READY_FOR_FORMALIZATION
    assert persisted_order.selected_trip_id == selected_trip_id
    assert response.load_order.status == LoadOrderStatus.READY_FOR_FORMALIZATION
    assert response.load_order.selected_trip_id == selected_trip_id
    assert [item.trip_id for item in response.candidates if item.is_selected] == [selected_trip_id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_select_carrier_replaces_previous_selection() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)
    snapshot = await _create_snapshot(session_factory, order.id)
    candidate_trip_ids = [
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    ]
    first_trip_id, second_trip_id = candidate_trip_ids[:2]

    async with session_factory() as session:
        first_response = await select_load_order_carrier(session, order.id, first_trip_id)
        await session.commit()

    async with session_factory() as session:
        second_response = await select_load_order_carrier(session, order.id, second_trip_id)
        await session.commit()

    assert first_response.load_order.selected_trip_id == first_trip_id
    assert second_response.load_order.selected_trip_id == second_trip_id
    assert [item.trip_id for item in second_response.candidates if item.is_selected] == [second_trip_id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_select_carrier_is_idempotent_for_same_trip() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)
    snapshot = await _create_snapshot(session_factory, order.id)
    selected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        first_response = await select_load_order_carrier(session, order.id, selected_trip_id)
        await session.commit()

    async with session_factory() as session:
        second_response = await select_load_order_carrier(session, order.id, selected_trip_id)
        await session.commit()

    assert first_response.load_order.selected_trip_id == selected_trip_id
    assert second_response.load_order.selected_trip_id == selected_trip_id
    assert [item.trip_id for item in second_response.candidates if item.is_selected] == [selected_trip_id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_select_carrier_allows_clearing_current_selection() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)
    snapshot = await _create_snapshot(session_factory, order.id)
    selected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        await select_load_order_carrier(session, order.id, selected_trip_id)
        await session.commit()

    async with session_factory() as session:
        response = await select_load_order_carrier(session, order.id, None)
        await session.commit()

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)

    assert persisted_order is not None
    assert persisted_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert persisted_order.selected_trip_id is None
    assert response.load_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert response.load_order.selected_trip_id is None
    assert [item.trip_id for item in response.candidates if item.is_selected] == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_reused_snapshot_keeps_ready_for_formalization_when_selection_exists() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)
    snapshot = await _create_snapshot(session_factory, order.id)
    selected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        await select_load_order_carrier(session, order.id, selected_trip_id)
        await session.commit()

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.status = LoadOrderStatus.VIABILITY_CONFIRMED
        await session.commit()

    async with session_factory() as session:
        reused_response, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    async with session_factory() as session:
        repaired_order = await session.get(LoadOrder, order.id)

    assert created is False
    assert repaired_order is not None
    assert repaired_order.status == LoadOrderStatus.READY_FOR_FORMALIZATION
    assert repaired_order.selected_trip_id == selected_trip_id
    assert reused_response.load_order.status == LoadOrderStatus.READY_FOR_FORMALIZATION
    assert reused_response.load_order.selected_trip_id == selected_trip_id
    assert [item.trip_id for item in reused_response.candidates if item.is_selected] == [selected_trip_id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_reused_snapshot_repairs_searching_carrier_to_ready_when_selection_is_valid() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)
    snapshot = await _create_snapshot(session_factory, order.id)
    selected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        await select_load_order_carrier(session, order.id, selected_trip_id)
        await session.commit()

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.status = LoadOrderStatus.SEARCHING_CARRIER
        await session.commit()

    async with session_factory() as session:
        reused_response, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    async with session_factory() as session:
        repaired_order = await session.get(LoadOrder, order.id)

    assert created is False
    assert repaired_order is not None
    assert repaired_order.status == LoadOrderStatus.READY_FOR_FORMALIZATION
    assert repaired_order.selected_trip_id == selected_trip_id
    assert reused_response.load_order.status == LoadOrderStatus.READY_FOR_FORMALIZATION
    assert reused_response.load_order.selected_trip_id == selected_trip_id
    assert [item.trip_id for item in reused_response.candidates if item.is_selected] == [selected_trip_id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_reused_snapshot_clears_rejected_selected_trip_and_repairs_to_searching() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order, _, rejected_trip_id = await _seed_order_with_rejections(session_factory, user.id)

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.selected_trip_id = rejected_trip_id
        persisted_order.status = LoadOrderStatus.VIABILITY_CONFIRMED
        await session.commit()

    async with session_factory() as session:
        reused_response, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    async with session_factory() as session:
        repaired_order = await session.get(LoadOrder, order.id)

    assert created is False
    assert repaired_order is not None
    assert repaired_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert repaired_order.selected_trip_id is None
    assert reused_response.load_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert reused_response.load_order.selected_trip_id is None
    assert [item.trip_id for item in reused_response.candidates if item.is_selected] == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_reused_snapshot_flushes_cleared_invalid_selection_from_searching_carrier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order, _, rejected_trip_id = await _seed_order_with_rejections(session_factory, user.id)

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.selected_trip_id = rejected_trip_id
        persisted_order.status = LoadOrderStatus.SEARCHING_CARRIER
        await session.commit()

    flush_calls = 0

    async with session_factory() as session:
        original_flush = session.flush

        async def noop_ensure_prototype_carriers(_session: AsyncSession) -> None:
            return None

        async def flush_spy(*args, **kwargs):
            nonlocal flush_calls
            flush_calls += 1
            return await original_flush(*args, **kwargs)

        monkeypatch.setattr(
            carrier_search_service,
            "ensure_canonical_carrier_catalog",
            noop_ensure_prototype_carriers,
        )
        monkeypatch.setattr(session, "flush", flush_spy)
        reused_response, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    async with session_factory() as session:
        repaired_order = await session.get(LoadOrder, order.id)

    assert created is False
    assert flush_calls == 1
    assert repaired_order is not None
    assert repaired_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert repaired_order.selected_trip_id is None
    assert reused_response.load_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert reused_response.load_order.selected_trip_id is None
    assert [item.trip_id for item in reused_response.candidates if item.is_selected] == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_reused_snapshot_repairs_ready_for_formalization_to_searching_when_selection_is_invalid() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order, _, rejected_trip_id = await _seed_order_with_rejections(session_factory, user.id)

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.selected_trip_id = rejected_trip_id
        persisted_order.status = LoadOrderStatus.READY_FOR_FORMALIZATION
        await session.commit()

    async with session_factory() as session:
        reused_response, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    async with session_factory() as session:
        repaired_order = await session.get(LoadOrder, order.id)

    assert created is False
    assert repaired_order is not None
    assert repaired_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert repaired_order.selected_trip_id is None
    assert reused_response.load_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert reused_response.load_order.selected_trip_id is None
    assert [item.trip_id for item in reused_response.candidates if item.is_selected] == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_reused_snapshot_clears_foreign_selected_trip_and_repairs_to_searching() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    first_order = await _seed_order(session_factory, user.id)
    second_order = await _seed_order(session_factory, user.id)
    await _create_snapshot(session_factory, first_order.id)
    second_snapshot = await _create_snapshot(session_factory, second_order.id)
    foreign_trip_id = next(
        item.trip_id for item in second_snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, first_order.id)
        assert persisted_order is not None
        persisted_order.selected_trip_id = foreign_trip_id
        persisted_order.status = LoadOrderStatus.VIABILITY_CONFIRMED
        await session.commit()

    async with session_factory() as session:
        reused_response, created = await create_load_order_carrier_search(session, first_order.id)
        await session.commit()

    async with session_factory() as session:
        repaired_order = await session.get(LoadOrder, first_order.id)

    assert created is False
    assert repaired_order is not None
    assert repaired_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert repaired_order.selected_trip_id is None
    assert reused_response.load_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert reused_response.load_order.selected_trip_id is None
    assert [item.trip_id for item in reused_response.candidates if item.is_selected] == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_formalize_requires_selected_candidate_trip_from_same_order() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    first_order = await _seed_order(session_factory, user.id)
    second_order = await _seed_order(session_factory, user.id)
    await _create_snapshot(session_factory, first_order.id)
    second_snapshot = await _create_snapshot(session_factory, second_order.id)
    foreign_trip_id = next(
        item.trip_id for item in second_snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, first_order.id)
        assert persisted_order is not None
        persisted_order.selected_trip_id = foreign_trip_id
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await formalize_load_order(session, first_order.id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Carrier selection required before ready_for_formalization"

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_ready_for_formalization_requires_candidate_selected_trip() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order, _, rejected_trip_id = await _seed_order_with_rejections(session_factory, user.id)

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.selected_trip_id = rejected_trip_id
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await update_load_order(
                session,
                order.id,
                LoadOrderUpdate(status=LoadOrderStatus.READY_FOR_FORMALIZATION),
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Carrier selection required before ready_for_formalization"

    await engine.dispose()


@pytest.mark.asyncio
async def test_formalize_promotes_ready_order_to_formalized() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)
    snapshot = await _create_snapshot(session_factory, order.id)
    selected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        await select_load_order_carrier(session, order.id, selected_trip_id)
        await session.commit()

    async with session_factory() as session:
        formalized = await formalize_load_order(session, order.id)

    assert formalized.status == LoadOrderStatus.FORMALIZED

    await engine.dispose()


@pytest.mark.asyncio
async def test_select_carrier_rejects_non_candidate_trip() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order, _, rejected_trip_id = await _seed_order_with_rejections(session_factory, user.id)

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await select_load_order_carrier(session, order.id, rejected_trip_id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Carrier selection requires a candidate trip"

    await engine.dispose()


@pytest.mark.asyncio
async def test_select_carrier_rejects_trip_from_other_order() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    first_order = await _seed_order(session_factory, user.id)
    second_order = await _seed_order(session_factory, user.id)
    first_snapshot = await _create_snapshot(session_factory, first_order.id)
    await _create_snapshot(session_factory, second_order.id)
    foreign_trip_id = next(
        item.trip_id
        for item in first_snapshot.candidates
        if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await select_load_order_carrier(session, second_order.id, foreign_trip_id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Trip not found for load order"

    await engine.dispose()


@pytest.mark.asyncio
async def test_select_carrier_requires_existing_snapshot() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await select_load_order_carrier(session, order.id, uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Load order has no carrier-search snapshot"

    await engine.dispose()


@pytest.mark.asyncio
async def test_select_carrier_rejects_non_selectable_order_status() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)
    snapshot = await _create_snapshot(session_factory, order.id)
    selected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.status = LoadOrderStatus.CANCELLED
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await select_load_order_carrier(session, order.id, selected_trip_id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Carrier selection not allowed for status: cancelled"

    await engine.dispose()
