from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.backend.models  # noqa: F401
from app.backend.core.domain_enums import (
    CarrierRejectionReason,
    LoadOrderStatus,
    TripProposalStatus,
)
from app.backend.db.base import Base
from app.backend.models.carrier import Carrier
from app.backend.models.load_order import LoadOrder
from app.backend.models.trip import Trip
from app.backend.models.truck_type import TruckType
from app.backend.models.user import User
from app.backend.services.load_order_carrier_search import _candidate_sort_key
from app.backend.services.load_order_carrier_search import create_load_order_carrier_search
from app.backend.services.load_order_carrier_search import get_load_order_carrier_candidates
from app.backend.services.carrier_catalog import CANONICAL_CARRIERS
from app.backend.schemas.carrier_search import CarrierCandidateResponse


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
    customer_price: Decimal | None = Decimal("1400.00"),
    distance_km: Decimal | None = Decimal("1000.00"),
    truck_type_id: int | None = 1,
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
        distance_km=distance_km,
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


async def _count_rows(session_factory: async_sessionmaker[AsyncSession], model) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.asyncio
async def test_create_carrier_search_snapshot_persists_initial_snapshot_and_transitions_order() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        response, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)

    assert created is True
    assert persisted_order is not None
    assert persisted_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert response.load_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert 3 <= len(response.candidates) <= 8
    assert await _count_rows(session_factory, Carrier) == 58
    assert await _count_rows(session_factory, Trip) == len(response.candidates)

    atlas = next(item for item in response.candidates if item.company_name == "Atlas Freight SL")
    assert atlas.proposal_status == TripProposalStatus.CANDIDATE
    assert atlas.ai_rejection_reason is None
    assert atlas.carrier_price == Decimal("780.00")
    assert atlas.profit_margin == Decimal("620.00")

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_carrier_search_snapshot_reuses_existing_trips_without_duplicates() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        first_response, first_created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    async with session_factory() as session:
        second_response, second_created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    assert first_created is True
    assert second_created is False
    assert await _count_rows(session_factory, Carrier) == 58
    assert await _count_rows(session_factory, Trip) == len(first_response.candidates)
    assert [item.trip_id for item in first_response.candidates] == [
        item.trip_id for item in second_response.candidates
    ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_carrier_search_snapshot_rejects_invalid_order_status() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(
        session_factory,
        user.id,
        status=LoadOrderStatus.VIABILITY_PENDING,
    )

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await create_load_order_carrier_search(session, order.id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Carrier search not allowed for status: viability_pending"

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_carrier_search_snapshot_returns_422_when_distance_is_missing() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id, distance_km=None)

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await create_load_order_carrier_search(session, order.id)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Carrier search requires distance_km"

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_carrier_search_snapshot_shortlist_prefers_reasonable_candidates() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        response, _ = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    assert 3 <= len(response.candidates) <= 8
    assert all(
        item.proposal_status == TripProposalStatus.CANDIDATE
        for item in response.candidates
    )

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_carrier_search_snapshot_can_include_rejections_when_candidates_are_limited() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id, adr_required=True)

    async with session_factory() as session:
        response, _ = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    assert 3 <= len(response.candidates) <= 8
    assert sum(
        1 for item in response.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    ) >= 3

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_carrier_search_snapshot_uses_shortlist_even_for_low_margin_orders() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(
        session_factory,
        user.id,
        customer_price=Decimal("700.00"),
    )

    async with session_factory() as session:
        response, _ = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    assert 3 <= len(response.candidates) <= 8
    assert all(
        item.profit_margin is not None
        for item in response.candidates
    )

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_carrier_search_snapshot_repairs_status_when_snapshot_exists() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        first_response, first_created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.status = LoadOrderStatus.VIABILITY_CONFIRMED
        await session.commit()

    async with session_factory() as session:
        second_response, second_created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    async with session_factory() as session:
        repaired_order = await session.get(LoadOrder, order.id)

    assert first_created is True
    assert second_created is False
    assert repaired_order is not None
    assert repaired_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert second_response.load_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert [item.trip_id for item in second_response.candidates] == [
        item.trip_id for item in first_response.candidates
    ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_reused_search_repairs_prototype_drift_but_get_is_read_only() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        initial_response, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    assert created is True

    atlas_id = next(
        carrier.id for carrier in CANONICAL_CARRIERS if carrier.company_name == "Atlas Freight SL"
    )

    async with session_factory() as session:
        atlas = await session.get(Carrier, atlas_id)
        truck_type = await session.get(TruckType, 1)
        assert atlas is not None
        assert truck_type is not None

        atlas.company_name = "Atlas Drifted"
        atlas.reliability_rating = Decimal("1.10")
        atlas.documentation_valid = False
        atlas.base_price_km = Decimal("9.9999")
        truck_type.name = "broken"
        await session.commit()

    async with session_factory() as session:
        reused_response, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()
        repaired_truck_type = await session.get(TruckType, 1)

    reused_atlas = next(item for item in reused_response.candidates if item.carrier_id == atlas_id)

    assert created is False
    assert repaired_truck_type is not None
    assert repaired_truck_type.name == "tautliner"
    assert reused_atlas.company_name == "Atlas Freight SL"
    assert reused_atlas.reliability_rating == Decimal("9.60")
    assert reused_atlas.documentation_valid is True
    assert reused_atlas.base_price_km == Decimal("0.7800")
    assert [item.trip_id for item in reused_response.candidates] == [
        item.trip_id for item in initial_response.candidates
    ]

    async with session_factory() as session:
        atlas = await session.get(Carrier, atlas_id)
        truck_type = await session.get(TruckType, 1)
        assert atlas is not None
        assert truck_type is not None

        atlas.company_name = "Atlas Drifted Again"
        atlas.reliability_rating = Decimal("2.20")
        truck_type.name = "still broken"
        await session.commit()

    async with session_factory() as session:
        fetched_response = await get_load_order_carrier_candidates(session, order.id)
        await session.commit()
        truck_type_after_get = await session.get(TruckType, 1)

    fetched_atlas = next(item for item in fetched_response.candidates if item.carrier_id == atlas_id)

    assert truck_type_after_get is not None
    assert truck_type_after_get.name == "still broken"
    assert fetched_atlas.company_name == "Atlas Freight SL"
    assert fetched_atlas.reliability_rating == Decimal("9.60")
    assert fetched_atlas.documentation_valid is True
    assert fetched_atlas.base_price_km == Decimal("0.7800")
    assert [item.trip_id for item in fetched_response.candidates] == [
        item.trip_id for item in initial_response.candidates
    ]

    async with session_factory() as session:
        atlas = await session.get(Carrier, atlas_id)

    assert atlas is not None
    assert atlas.company_name == "Atlas Drifted Again"
    assert atlas.reliability_rating == Decimal("2.20")

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_carrier_candidates_projects_invalid_selection_coherently_without_mutation() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        snapshot, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    assert created is True

    if not any(item.proposal_status == TripProposalStatus.REJECTED for item in snapshot.candidates):
        pytest.skip("Shortlist contained only candidate rows")

    rejected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.REJECTED
    )

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.selected_trip_id = rejected_trip_id
        persisted_order.status = LoadOrderStatus.READY_FOR_FORMALIZATION
        await session.commit()

    async with session_factory() as session:
        response = await get_load_order_carrier_candidates(session, order.id)
        await session.commit()

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)

    assert persisted_order is not None
    assert persisted_order.status == LoadOrderStatus.READY_FOR_FORMALIZATION
    assert persisted_order.selected_trip_id == rejected_trip_id
    assert response.load_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert response.load_order.selected_trip_id is None
    assert [item.trip_id for item in response.candidates if item.is_selected] == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_carrier_candidates_projects_valid_selection_coherently_without_mutation() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        snapshot, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    assert created is True

    selected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.selected_trip_id = selected_trip_id
        persisted_order.status = LoadOrderStatus.SEARCHING_CARRIER
        await session.commit()

    async with session_factory() as session:
        response = await get_load_order_carrier_candidates(session, order.id)
        await session.commit()

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)

    assert persisted_order is not None
    assert persisted_order.status == LoadOrderStatus.SEARCHING_CARRIER
    assert persisted_order.selected_trip_id == selected_trip_id
    assert response.load_order.status == LoadOrderStatus.READY_FOR_FORMALIZATION
    assert response.load_order.selected_trip_id == selected_trip_id
    assert [item.trip_id for item in response.candidates if item.is_selected] == [selected_trip_id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_carrier_candidates_preserves_cancelled_status_while_projecting_selection() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        snapshot, created = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    assert created is True

    selected_trip_id = next(
        item.trip_id for item in snapshot.candidates if item.proposal_status == TripProposalStatus.CANDIDATE
    )

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)
        assert persisted_order is not None
        persisted_order.selected_trip_id = selected_trip_id
        persisted_order.status = LoadOrderStatus.CANCELLED
        await session.commit()

    async with session_factory() as session:
        response = await get_load_order_carrier_candidates(session, order.id)
        await session.commit()

    async with session_factory() as session:
        persisted_order = await session.get(LoadOrder, order.id)

    assert persisted_order is not None
    assert persisted_order.status == LoadOrderStatus.CANCELLED
    assert persisted_order.selected_trip_id == selected_trip_id
    assert response.load_order.status == LoadOrderStatus.CANCELLED
    assert response.load_order.selected_trip_id == selected_trip_id
    assert [item.trip_id for item in response.candidates if item.is_selected] == [selected_trip_id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_carrier_search_snapshot_sorts_candidates_before_rejections() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    async with session_factory() as session:
        response, _ = await create_load_order_carrier_search(session, order.id)
        await session.commit()

    assert 3 <= len(response.candidates) <= 8

    # All candidates should have ranking_score and agent_reasoning
    for candidate in response.candidates:
        assert candidate.ranking_score is not None
        assert candidate.agent_reasoning is not None
        assert candidate.score_breakdown is not None

    rejected_indexes = [
        index
        for index, item in enumerate(response.candidates)
        if item.proposal_status == TripProposalStatus.REJECTED
    ]
    if rejected_indexes:
        first_rejected_index = rejected_indexes[0]
        assert all(
            item.proposal_status == TripProposalStatus.CANDIDATE
            for item in response.candidates[:first_rejected_index]
        )
        assert all(
            item.proposal_status == TripProposalStatus.REJECTED
            for item in response.candidates[first_rejected_index:]
        )
    else:
        assert all(
            item.proposal_status == TripProposalStatus.CANDIDATE
            for item in response.candidates
        )

    # Candidates should be sorted by ranking_score descending
    candidate_scores = [
        item.ranking_score
        for item in response.candidates
        if item.proposal_status == TripProposalStatus.CANDIDATE
    ]
    assert candidate_scores == sorted(candidate_scores, reverse=True)

    await engine.dispose()


def test_candidate_sort_key_sorts_rejected_rows_by_company_name_when_tied() -> None:
    candidates = [
        CarrierCandidateResponse(
            trip_id=uuid4(),
            carrier_id=uuid4(),
            company_name="Jano Fleet",
            truck_type_id=3,
            reliability_rating=Decimal("9.10"),
            documentation_valid=True,
            adr_capable=True,
            base_price_km=Decimal("1.1800"),
            carrier_price=Decimal("1180.00"),
            profit_margin=Decimal("220.00"),
            proposal_status=TripProposalStatus.REJECTED,
            ai_rejection_reason=CarrierRejectionReason.TRUCK_TYPE_MISMATCH,
        ),
        CarrierCandidateResponse(
            trip_id=uuid4(),
            carrier_id=uuid4(),
            company_name="Costa Reefer Lines",
            truck_type_id=2,
            reliability_rating=Decimal("9.10"),
            documentation_valid=True,
            adr_capable=False,
            base_price_km=Decimal("0.9500"),
            carrier_price=Decimal("950.00"),
            profit_margin=Decimal("450.00"),
            proposal_status=TripProposalStatus.REJECTED,
            ai_rejection_reason=CarrierRejectionReason.TRUCK_TYPE_MISMATCH,
        ),
    ]

    assert [candidate.company_name for candidate in sorted(candidates, key=_candidate_sort_key)] == [
        "Costa Reefer Lines",
        "Jano Fleet",
    ]


class TestCarrierCloudEvaluation:
    def test_validate_carrier_evaluation_accepts_valid_output(self) -> None:
        from app.backend.services.load_order_carrier_search import (
            CarrierEvaluation,
            CarrierEvaluationList,
            _validate_carrier_evaluation,
        )

        valid = {
            "candidates": [
                {
                    "carrier_id": "atlas-freight-sl",
                    "proposal_status": "candidate",
                    "rejection_reason": None,
                    "ranking_score": 85.0,
                    "score_breakdown": {"route_match": 80.0, "price": 90.0},
                    "agent_reasoning": "Strong route match.",
                },
                {
                    "carrier_id": "helix-transport",
                    "proposal_status": "rejected",
                    "rejection_reason": "invalid_documentation",
                    "ranking_score": 0.0,
                    "score_breakdown": {},
                    "agent_reasoning": "Invalid docs.",
                },
            ]
        }

        result = _validate_carrier_evaluation(valid)
        assert isinstance(result, CarrierEvaluationList)
        assert len(result.candidates) == 2
        assert result.candidates[0].proposal_status == "candidate"
        assert result.candidates[1].rejection_reason == "invalid_documentation"

    def test_validate_carrier_evaluation_rejects_malformed_output(self) -> None:
        from app.backend.services.load_order_carrier_search import (
            CarrierEvaluationList,
            _validate_carrier_evaluation,
        )

        result = _validate_carrier_evaluation({"bad": "data"})
        assert isinstance(result, CarrierEvaluationList)
        assert result.candidates == []

    def test_carrier_evaluation_schema(self) -> None:
        from app.backend.services.load_order_carrier_search import CarrierEvaluation

        ev = CarrierEvaluation(
            carrier_id="atlas-freight-sl",
            proposal_status="candidate",
            rejection_reason=None,
            ranking_score=92.5,
            score_breakdown={"route_match": 95.0},
            agent_reasoning="Best fit for route.",
        )
        assert ev.carrier_id == "atlas-freight-sl"
        assert ev.proposal_status == "candidate"
        assert ev.ranking_score == 92.5

    @pytest.mark.asyncio
    async def test_evaluate_carriers_with_reasoning_uses_cloud_profile(self) -> None:
        from unittest.mock import AsyncMock, patch
        from app.backend.services.load_order_carrier_search import _evaluate_carriers_with_reasoning
        from app.backend.core.settings import Settings
        from decimal import Decimal

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )

        model_output = {
            "candidates": [
                {
                    "carrier_id": "atlas-freight-sl",
                    "proposal_status": "candidate",
                    "rejection_reason": None,
                    "ranking_score": 88.0,
                    "score_breakdown": {"route_match": 90.0},
                    "agent_reasoning": "Good route match and competitive pricing.",
                },
                {
                    "carrier_id": "boreal-cargo",
                    "proposal_status": "rejected",
                    "rejection_reason": "adr_not_supported",
                    "ranking_score": 0.0,
                    "score_breakdown": {},
                    "agent_reasoning": "ADR required but not supported.",
                },
            ]
        }

        mock_result = AsyncMock()
        mock_result.content = model_output

        with patch(
            "app.backend.services.model_runtime_gateway.structured_completion",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_completion:
            result = await _evaluate_carriers_with_reasoning(
                settings=settings,
                order_context="Test order",
                carrier_names=["Atlas Freight SL", "Boreal Cargo"],
            )

        assert len(result.candidates) == 2
        assert result.candidates[0].proposal_status == "candidate"
        assert result.candidates[1].rejection_reason == "adr_not_supported"

        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["profile"] == "reasoning_json"
        assert call_kwargs["settings"] == settings


@pytest.mark.asyncio
async def test_carrier_search_fallback_is_explicit_when_cloud_reasoning_fails() -> None:
    from app.backend.core.settings import Settings

    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///./tests.db",
        REASONING_MODEL_PROVIDER="openrouter",
        REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
        REASONING_MODEL_API_KEY="sk-test",
    )

    async with session_factory() as session:
        with patch(
            "app.backend.core.settings.get_settings",
            return_value=settings,
        ):
            with patch(
                "app.backend.services.model_runtime_gateway.structured_completion",
                new_callable=AsyncMock,
                side_effect=RuntimeError("cloud down"),
            ):
                response, _ = await create_load_order_carrier_search(session, order.id)
                await session.commit()

    atlas = next(item for item in response.candidates if item.company_name == "Atlas Freight SL")
    assert atlas.agent_reasoning is not None
    assert atlas.agent_reasoning.startswith("Fallback heuristic evaluation:")

    await engine.dispose()


@pytest.mark.asyncio
async def test_carrier_search_cloud_reasoning_only_evaluates_shortlist() -> None:
    from app.backend.core.settings import Settings
    from app.backend.services.load_order_carrier_search import CarrierEvaluationList

    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///./tests.db",
        REASONING_MODEL_PROVIDER="openrouter",
        REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
        REASONING_MODEL_API_KEY="sk-test",
    )

    async def _fake_reasoning(*, settings, order_context, carrier_names):
        del settings, order_context
        return CarrierEvaluationList(candidates=[
            {
                "carrier_id": name.lower().replace(" ", "-"),
                "proposal_status": "candidate",
                "rejection_reason": None,
                "ranking_score": 80.0 - index,
                "score_breakdown": {
                    "route_match": 80.0,
                    "price_competitiveness": 80.0,
                    "reliability": 80.0,
                    "truck_adr_compatibility": 80.0,
                },
                "agent_reasoning": f"Fit check for {name}.",
            }
            for index, name in enumerate(carrier_names)
        ])

    async with session_factory() as session:
        with patch(
            "app.backend.core.settings.get_settings",
            return_value=settings,
        ):
            with patch(
                "app.backend.services.load_order_carrier_search._evaluate_carriers_with_reasoning",
                new_callable=AsyncMock,
                side_effect=_fake_reasoning,
            ) as mock_reasoning:
                response, _ = await create_load_order_carrier_search(session, order.id)
                await session.commit()

    evaluated_carriers = mock_reasoning.call_args.kwargs["carrier_names"]

    assert len(evaluated_carriers) <= 8
    assert len(response.candidates) <= 8
    assert all(
        candidate.agent_reasoning.startswith("Cloud reasoning:")
        for candidate in response.candidates
    )

    await engine.dispose()


# ─── Carrier search retrieval tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_carrier_search_works_when_chroma_empty() -> None:
    from app.backend.services.runtime_settings import invalidate_boolean_settings_cache
    invalidate_boolean_settings_cache()

    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    try:
        async with session_factory() as session:
            order = await session.get(LoadOrder, order.id)
            response, created = await create_load_order_carrier_search(session, order.id)
            await session.commit()

            assert created
            assert len(response.candidates) > 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_carrier_search_fallback_heuristic_still_works() -> None:
    from app.backend.services.runtime_settings import invalidate_boolean_settings_cache
    invalidate_boolean_settings_cache()

    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _seed_order(session_factory, user.id)

    try:
        async with session_factory() as session:
            order = await session.get(LoadOrder, order.id)
            with patch(
                "app.backend.core.settings.get_settings",
                return_value=type("StubSettings", (), {
                    "reasoning_model_name": "test-model",
                    "reasoning_model_provider": "test",
                })(),
            ):
                with patch(
                    "app.backend.services.load_order_carrier_search._evaluate_carriers_cloud",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("simulated cloud failure"),
                ):
                    response, created = await create_load_order_carrier_search(session, order.id)
                    await session.commit()

            assert created
            assert len(response.candidates) > 0
            assert any("Fallback" in (c.agent_reasoning or "") for c in response.candidates)
    finally:
        await engine.dispose()
