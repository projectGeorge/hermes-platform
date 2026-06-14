from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.backend.models  # noqa: F401
from app.backend.core.domain_enums import LoadOrderHumanReviewStatus, LoadOrderStatus
from app.backend.db.base import Base
from app.backend.models.load_order import LoadOrder
from app.backend.models.load_order_human_review import LoadOrderHumanReview
from app.backend.models.user import User
from app.backend.schemas.human_validation import (
    HumanValidationConfirmRequest,
    HumanValidationUpdateRequest,
)
from app.backend.services.load_order_human_validation import (
    confirm_load_order_viability,
    get_load_order_human_validation_context,
    update_load_order_human_validation,
)
from app.backend.services.load_orders import create_load_order
from app.backend.schemas.load_order import LoadOrderCreate
from app.backend.services.load_order_ingestion import ingest_load_order_from_raw_text


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


async def _ingest_order(
    session_factory: async_sessionmaker[AsyncSession],
    user_id,
    raw_text: str,
):
    async with session_factory() as session:
        response = await ingest_load_order_from_raw_text(session, user_id, raw_text)
        await session.commit()

    return response


async def _create_manual_order(
    session_factory: async_sessionmaker[AsyncSession],
    user_id,
) -> LoadOrder:
    async with session_factory() as session:
        order = await create_load_order(
            session,
            LoadOrderCreate(
                user_id=user_id,
                customer_name="Manual Logistics",
                status=LoadOrderStatus.PENDING_INGESTION,
                origin_text="Madrid, ES",
                cargo_description="Manual order",
                currency="EUR",
            ),
        )
        await session.commit()
        runtime_order = await session.get(LoadOrder, order.id)
        assert runtime_order is not None
        return runtime_order


async def _count_reviews(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(LoadOrderHumanReview)) or 0)


async def _list_reviews(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[LoadOrderHumanReview]:
    async with session_factory() as session:
        result = await session.execute(
            select(LoadOrderHumanReview).order_by(
                LoadOrderHumanReview.created_at,
                LoadOrderHumanReview.id,
            )
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_get_human_validation_context_returns_current_review_state() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)

    ingestion = await _ingest_order(
        session_factory,
        user.id,
        """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip(),
    )

    async with session_factory() as session:
        context = await get_load_order_human_validation_context(session, ingestion.load_order.id)

    assert context.load_order.status == LoadOrderStatus.VIABILITY_PENDING
    assert context.load_order.missing_fields == {
        "weight_kg": "not_found",
        "customer_price": "not_found",
    }
    assert context.missing_fields == {
        "weight_kg": "not_found",
        "customer_price": "not_found",
    }
    assert context.blocked_missing_fields == {}
    assert context.latest_ingestion_run.route == "load_order_ingestion"
    assert context.latest_ingestion_run.raw_text.startswith("Customer: Acme Logistics")
    assert context.latest_ingestion_run.extracted_payload["origin_text"] == "Madrid, ES"
    assert "customer_name" in context.reviewable_fields
    assert "weight_kg" in context.reviewable_fields
    assert context.can_confirm_viability is False

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_human_validation_context_synthesizes_manual_review_context() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _create_manual_order(session_factory, user.id)

    async with session_factory() as session:
        context = await get_load_order_human_validation_context(session, order.id)
        await session.commit()

    assert context.load_order.status == LoadOrderStatus.PENDING_INGESTION
    assert context.latest_ingestion_run.route == "manual_order_review"
    assert context.latest_ingestion_run.execution_path == "manual"
    assert context.latest_ingestion_run.provider == "operator"
    assert "Manual Logistics" in context.latest_ingestion_run.raw_text
    assert context.can_confirm_viability is False

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_human_validation_promotes_manual_order_to_viability_pending() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)
    order = await _create_manual_order(session_factory, user.id)

    async with session_factory() as session:
        context = await update_load_order_human_validation(
            session,
            order.id,
            HumanValidationUpdateRequest(
                reviewed_by_user_id=user.id,
                destination_text="Paris, FR",
                origin_load_date=datetime(2026, 5, 4, 9, 30),
                weight_kg=Decimal("7800.00"),
                customer_price=Decimal("1250.50"),
            ),
        )
        await session.commit()

    assert context.load_order.status == LoadOrderStatus.VIABILITY_PENDING
    assert context.missing_fields == {}
    assert context.can_confirm_viability is True
    assert context.latest_ingestion_run.route == "manual_order_review"

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_human_validation_promotes_pending_ingestion_when_model_fields_are_completed() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)

    ingestion = await _ingest_order(
        session_factory,
        user.id,
        """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
""".strip(),
    )

    async with session_factory() as session:
        context = await update_load_order_human_validation(
            session,
            ingestion.load_order.id,
            HumanValidationUpdateRequest(
                reviewed_by_user_id=user.id,
                origin_load_date=datetime(2026, 5, 4, 9, 30),
                cargo_description="Ceramic tiles",
            ),
        )
        await session.commit()

    reviews = await _list_reviews(session_factory)

    assert context.load_order.status == LoadOrderStatus.VIABILITY_PENDING
    assert context.missing_fields == {
        "weight_kg": "not_found",
        "customer_price": "not_found",
    }
    assert context.blocked_missing_fields == {}
    assert len(reviews) == 1
    assert reviews[0].review_status == LoadOrderHumanReviewStatus.FIELDS_UPDATED
    assert reviews[0].submitted_fields["cargo_description"] == "Ceramic tiles"
    assert reviews[0].remaining_missing_fields == {
        "weight_kg": "not_found",
        "customer_price": "not_found",
    }

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_human_validation_completes_pending_ingestion_when_text_field_is_reviewed() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)

    ingestion = await _ingest_order(
        session_factory,
        user.id,
        """
Customer: Acme Logistics
Origin: Madrid, ES
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip(),
    )

    async with session_factory() as session:
        context = await update_load_order_human_validation(
            session,
            ingestion.load_order.id,
            HumanValidationUpdateRequest(
                reviewed_by_user_id=user.id,
                destination_text="Paris, FR",
                weight_kg=Decimal("7800.00"),
                customer_price=Decimal("1250.50"),
            ),
        )
        await session.commit()

    reviews = await _list_reviews(session_factory)

    assert context.load_order.status == LoadOrderStatus.VIABILITY_PENDING
    assert context.load_order.destination_text == "Paris, FR"
    assert context.missing_fields == {}
    assert context.blocked_missing_fields == {}
    assert context.can_confirm_viability is True
    assert reviews[0].submitted_fields["destination_text"] == "Paris, FR"

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_human_validation_context_reads_persisted_textual_fields_from_load_order() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)

    ingestion = await _ingest_order(
        session_factory,
        user.id,
        """
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip(),
    )

    async with session_factory() as session:
        context = await update_load_order_human_validation(
            session,
            ingestion.load_order.id,
            HumanValidationUpdateRequest(
                reviewed_by_user_id=user.id,
                customer_name="Acme Logistics",
            ),
        )
        await session.commit()

    assert context.load_order.customer_name == "Acme Logistics"
    assert context.missing_fields == {
        "weight_kg": "not_found",
        "customer_price": "not_found",
    }
    assert context.blocked_missing_fields == {}

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_human_validation_makes_viability_pending_order_confirmable() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)

    ingestion = await _ingest_order(
        session_factory,
        user.id,
        """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip(),
    )

    async with session_factory() as session:
        context = await update_load_order_human_validation(
            session,
            ingestion.load_order.id,
            HumanValidationUpdateRequest(
                reviewed_by_user_id=user.id,
                weight_kg=Decimal("7800.00"),
                customer_price=Decimal("1250.50"),
                review_notes="Confirmed figures with customer",
            ),
        )
        await session.commit()

    reviews = await _list_reviews(session_factory)

    assert context.load_order.status == LoadOrderStatus.VIABILITY_PENDING
    assert context.missing_fields == {}
    assert context.can_confirm_viability is True
    assert len(reviews) == 1
    assert reviews[0].review_status == LoadOrderHumanReviewStatus.FIELDS_UPDATED
    assert reviews[0].review_notes == "Confirmed figures with customer"
    assert set(reviews[0].submitted_fields) == {"weight_kg", "customer_price"}
    assert reviews[0].remaining_missing_fields == {}

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_human_validation_rejects_degrading_edit_from_viability_pending() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)

    ingestion = await _ingest_order(
        session_factory,
        user.id,
        """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip(),
    )

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await update_load_order_human_validation(
                session,
                ingestion.load_order.id,
                HumanValidationUpdateRequest(
                    reviewed_by_user_id=user.id,
                    cargo_description=None,
                ),
            )

        order = await session.get(LoadOrder, ingestion.load_order.id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Human validation update would make the order non-reviewable"
    assert order is not None
    assert order.status == LoadOrderStatus.VIABILITY_PENDING
    assert await _count_reviews(session_factory) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_load_order_viability_rejects_when_missing_fields_remain() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)

    ingestion = await _ingest_order(
        session_factory,
        user.id,
        """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip(),
    )

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await confirm_load_order_viability(
                session,
                ingestion.load_order.id,
                HumanValidationConfirmRequest(reviewed_by_user_id=user.id),
            )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Cannot confirm viability while missing_fields remain"
    assert await _count_reviews(session_factory) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_load_order_viability_persists_audit_event() -> None:
    engine, session_factory = await _build_session_factory()
    user = await _seed_user(session_factory)

    ingestion = await _ingest_order(
        session_factory,
        user.id,
        """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip(),
    )

    async with session_factory() as session:
        await update_load_order_human_validation(
            session,
            ingestion.load_order.id,
            HumanValidationUpdateRequest(
                reviewed_by_user_id=user.id,
                weight_kg=Decimal("7800.00"),
                customer_price=Decimal("1250.50"),
            ),
        )
        await session.commit()

    async with session_factory() as session:
        confirmed_order = await confirm_load_order_viability(
            session,
            ingestion.load_order.id,
            HumanValidationConfirmRequest(
                reviewed_by_user_id=user.id,
                review_notes="Viability confirmed by operator",
            ),
        )
        await session.commit()

    reviews = await _list_reviews(session_factory)

    assert confirmed_order.status == LoadOrderStatus.VIABILITY_CONFIRMED
    assert len(reviews) == 2
    confirmation_review = next(
        review
        for review in reviews
        if review.review_status == LoadOrderHumanReviewStatus.VIABILITY_CONFIRMED
    )
    assert confirmation_review.review_notes == "Viability confirmed by operator"
    assert confirmation_review.remaining_missing_fields == {}

    await engine.dispose()
