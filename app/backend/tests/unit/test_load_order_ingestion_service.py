from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.backend.models  # noqa: F401
from app.backend.core.domain_enums import (
    IngestionRunStatus,
    LOAD_ORDER_INGESTION_ROUTE,
    LoadOrderStatus,
)
from app.backend.db.base import Base
from app.backend.models.ingestion_run import IngestionRun
from app.backend.models.load_order import LoadOrder
from app.backend.models.user import User
from app.backend.services.load_order_ingestion import (
    RawTextLoadOrderParserError,
    ingest_load_order_from_raw_text,
    parse_load_order_raw_text,
)
from app.backend.services.ingestion_model_runtime import ModelExtractionResult


def test_parse_load_order_raw_text_extracts_deterministic_payload() -> None:
    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
Price: 1250.50
Weight: 7800
ADR: yes
""".strip()

    extracted = parse_load_order_raw_text(raw_text)

    assert extracted == {
        "customer_name": "Acme Logistics",
        "origin_text": "Madrid, ES",
        "destination_text": "Paris, FR",
        "origin_load_date": "2026-05-04T09:30:00",
        "cargo_description": "Ceramic tiles",
        "customer_price": "1250.50",
        "weight_kg": "7800",
        "adr_required": True,
        "currency": "EUR",
    }


def test_parse_load_order_raw_text_extracts_common_email_variants() -> None:
    raw_text = """
Subject: New shipment request
Customer: Acme Logistics
Pickup: Madrid, ES
Delivery: Paris, FR
Loading date: 2026-05-04 09:30
Commodity: Ceramic tiles
Weight: 7800
Price: 1250.50 EUR
""".strip()

    extracted = parse_load_order_raw_text(raw_text)

    assert extracted["customer_name"] == "Acme Logistics"
    assert extracted["origin_text"] == "Madrid, ES"
    assert extracted["destination_text"] == "Paris, FR"
    assert extracted["origin_load_date"] == "2026-05-04T09:30:00"
    assert extracted["cargo_description"] == "Ceramic tiles"
    assert extracted["weight_kg"] == "7800"
    assert extracted["customer_price"] == "1250.50"
    assert extracted["currency"] == "EUR"


def test_parse_load_order_raw_text_extracts_spanish_email_variants() -> None:
    raw_text = """
Cliente: ElectroHispana S.L.
Origen: Valencia, ES
Destino: Frankfurt, DE
Descripcion de la carga: 10 palets americanos con bobinas de cableado industrial.
Presupuesto: 2400 EUR
""".strip()

    extracted = parse_load_order_raw_text(raw_text)

    assert extracted["customer_name"] == "ElectroHispana S.L."
    assert extracted["origin_text"] == "Valencia, ES"
    assert extracted["destination_text"] == "Frankfurt, DE"
    assert extracted["cargo_description"] == "10 palets americanos con bobinas de cableado industrial."
    assert extracted["customer_price"] == "2400"
    assert extracted["currency"] == "EUR"


def test_parse_load_order_raw_text_extracts_operational_spanish_email_shape() -> None:
    raw_text = """
Asunto: Confirmacion de carga - Ruta Bilbao a Oporto

Origen: Bilbao, ES
Destino: Porto, PT
Precio cliente: 1.100 EUR
Peso: 18.500 kg
Tipo de camion: Tautliner
ADR: No requerido
""".strip()

    extracted = parse_load_order_raw_text(raw_text)

    assert extracted["origin_text"] == "Bilbao, ES"
    assert extracted["destination_text"] == "Porto, PT"
    assert extracted["customer_price"] == "1100"
    assert extracted["weight_kg"] == "18500"
    assert extracted["truck_type_id"] == 1
    assert extracted["adr_required"] is False
    assert extracted["currency"] == "EUR"


def test_parse_load_order_raw_text_accepts_adr_value_with_parenthetical_details() -> None:
    raw_text = """
Cliente: SurQuimica Global S.L.
Origen: Sevilla, ES
Destino: Rotterdam, NL
Fecha de carga: 2026-05-04 09:30
Descripcion de la carga: Palets de producto quimico de limpieza
ADR: Requerido (Clase 9, mercancias peligrosas diversas)
""".strip()

    extracted = parse_load_order_raw_text(raw_text)

    assert extracted["adr_required"] is True


def test_parse_load_order_raw_text_infers_company_name_from_signature() -> None:
    raw_text = """
Asunto: Nueva orden de transporte - Sevilla a Rotterdam

Hola, equipo:

Origen: Sevilla, ES
Destino: Rotterdam, NL
Fecha de carga: 2026-05-04 09:30
Descripcion de la carga: Palets de producto químico de limpieza
Tipo de camión: tautliner

Saludos cordiales,
Carmen Ortiz
Export Manager | SurQuimica Global S.L.
""".strip()

    extracted = parse_load_order_raw_text(raw_text)

    assert extracted["customer_name"] == "SurQuimica Global S.L."
    assert extracted["truck_type_id"] == 1


@pytest.mark.asyncio
async def test_ingest_load_order_creates_viability_pending_run() -> None:
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

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
Price: 1250.50
Weight: 7800
ADR: yes
""".strip()

    async with session_factory() as session:
        response = await ingest_load_order_from_raw_text(session, user.id, raw_text)
        await session.commit()

        run = await session.get(IngestionRun, response.ingestion_run_id)
        load_order = await session.get(LoadOrder, response.load_order.id)

    assert response.route == LOAD_ORDER_INGESTION_ROUTE
    assert response.run_status == IngestionRunStatus.COMPLETED
    assert response.load_order.status == LoadOrderStatus.VIABILITY_PENDING
    assert response.load_order.customer_id is None
    assert response.load_order.customer_name == "Acme Logistics"
    assert response.load_order.origin_id is None
    assert response.load_order.origin_text == "Madrid, ES"
    assert response.load_order.destination_id is None
    assert response.load_order.destination_text == "Paris, FR"
    assert response.load_order.currency == "EUR"
    assert response.missing_fields == {}
    assert response.extracted_payload["customer_name"] == "Acme Logistics"
    assert run is not None
    assert run.status == IngestionRunStatus.COMPLETED
    assert run.route == LOAD_ORDER_INGESTION_ROUTE
    assert run.load_order_id == response.load_order.id
    assert run.error_detail is None
    assert load_order is not None
    assert load_order.status == LoadOrderStatus.VIABILITY_PENDING

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_keeps_viability_pending_with_non_blocking_missing_fields() -> None:
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

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip()

    async with session_factory() as session:
        response = await ingest_load_order_from_raw_text(session, user.id, raw_text)
        await session.commit()

        run = await session.get(IngestionRun, response.ingestion_run_id)

    assert response.run_status == IngestionRunStatus.COMPLETED
    assert response.load_order.status == LoadOrderStatus.VIABILITY_PENDING
    assert response.missing_fields == {
        "customer_price": "not_found",
        "weight_kg": "not_found",
    }
    assert run is not None
    assert run.status == IngestionRunStatus.COMPLETED
    assert run.missing_fields == {
        "customer_price": "not_found",
        "weight_kg": "not_found",
    }

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_falls_back_to_pending_ingestion_when_minimum_missing() -> None:
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

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Cargo: Ceramic tiles
""".strip()

    async with session_factory() as session:
        response = await ingest_load_order_from_raw_text(session, user.id, raw_text)
        await session.commit()

    assert response.run_status == IngestionRunStatus.COMPLETED
    assert response.load_order.status == LoadOrderStatus.PENDING_INGESTION
    assert response.load_order.currency == "EUR"
    assert response.load_order.customer_name == "Acme Logistics"
    assert response.load_order.origin_text == "Madrid, ES"
    assert response.load_order.destination_text is None
    assert response.missing_fields == {
        "destination_text": "not_found",
        "origin_load_date": "not_found",
        "customer_price": "not_found",
        "weight_kg": "not_found",
    }

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_raises_404_before_creating_run_for_unknown_user() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await ingest_load_order_from_raw_text(
                session,
                uuid4(),
                "Customer: Ghost Logistics",
            )

        result = await session.execute(select(IngestionRun))
        runs = list(result.scalars().all())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "User not found"
    assert runs == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_marks_run_failed_on_internal_parser_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    def raise_parser_error(_: str) -> dict[str, object]:
        raise RawTextLoadOrderParserError("parser exploded")

    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.parse_load_order_raw_text",
        raise_parser_error,
    )

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await ingest_load_order_from_raw_text(session, user.id, "Customer: Acme Logistics")

        result = await session.execute(select(IngestionRun))
        runs = list(result.scalars().all())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Load order ingestion failed"
    assert len(runs) == 1
    assert runs[0].status == IngestionRunStatus.FAILED
    assert runs[0].error_detail == "parser exploded"
    assert runs[0].load_order_id is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_persists_failed_run_after_db_error_across_session_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    async def raise_db_error(session: AsyncSession, payload: object) -> LoadOrder:
        broken_order = LoadOrder(user_id=None, currency="EUR")
        session.add(broken_order)
        await session.flush()
        raise AssertionError("unreachable")

    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.create_load_order",
        raise_db_error,
    )

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await ingest_load_order_from_raw_text(session, user.id, raw_text)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Load order ingestion failed"

    async with session_factory() as session:
        result = await session.execute(select(IngestionRun))
        runs = list(result.scalars().all())

    assert len(runs) == 1
    assert runs[0].status == IngestionRunStatus.FAILED
    assert runs[0].error_detail is not None
    assert runs[0].load_order_id is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_persists_failed_run_across_session_boundary() -> None:
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

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026/05/04 09:30
Cargo: Ceramic tiles
""".strip()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await ingest_load_order_from_raw_text(session, user.id, raw_text)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "invalid load date format"

    async with session_factory() as session:
        result = await session.execute(select(IngestionRun))
        runs = list(result.scalars().all())

    assert len(runs) == 1
    assert runs[0].status == IngestionRunStatus.FAILED
    assert runs[0].error_detail == "invalid load date format"
    assert runs[0].load_order_id is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_marks_run_failed_for_downstream_http_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    async def raise_downstream_http_error(*_: object, **__: object) -> LoadOrder:
        raise HTTPException(status_code=422, detail="downstream validation error")

    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.create_load_order",
        raise_downstream_http_error,
    )

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await ingest_load_order_from_raw_text(session, user.id, raw_text)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "downstream validation error"

    async with session_factory() as session:
        result = await session.execute(select(IngestionRun))
        runs = list(result.scalars().all())

    assert len(runs) == 1
    assert runs[0].status == IngestionRunStatus.FAILED
    assert runs[0].error_detail == "downstream validation error"
    assert runs[0].load_order_id is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_marks_run_failed_on_validation_error_422() -> None:
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

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
Price: -950.00
""".strip()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await ingest_load_order_from_raw_text(session, user.id, raw_text)

        result = await session.execute(select(IngestionRun))
        runs = list(result.scalars().all())

    assert exc_info.value.status_code == 422
    assert "customer_price" in str(exc_info.value.detail)
    assert len(runs) == 1
    assert runs[0].status == IngestionRunStatus.FAILED
    assert "customer_price" in str(runs[0].error_detail)
    assert runs[0].load_order_id is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_surfaces_invalid_load_date_as_422_and_failed_run() -> None:
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

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026/05/04 09:30
Cargo: Ceramic tiles
""".strip()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await ingest_load_order_from_raw_text(session, user.id, raw_text)

        result = await session.execute(select(IngestionRun))
        runs = list(result.scalars().all())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "invalid load date format"
    assert len(runs) == 1
    assert runs[0].status == IngestionRunStatus.FAILED
    assert runs[0].error_detail == "invalid load date format"
    assert runs[0].load_order_id is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_surfaces_invalid_adr_token_as_422_and_failed_run() -> None:
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

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
ADR: maybe
""".strip()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await ingest_load_order_from_raw_text(session, user.id, raw_text)

        result = await session.execute(select(IngestionRun))
        runs = list(result.scalars().all())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "invalid adr value"
    assert len(runs) == 1
    assert runs[0].status == IngestionRunStatus.FAILED
    assert runs[0].error_detail == "invalid adr value"
    assert runs[0].load_order_id is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_runs_model_path_and_persists_execution_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    mock_result = ModelExtractionResult(
        extracted_payload={
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "origin_load_date": "2026-05-04T09:30:00",
            "cargo_description": "Ceramic tiles",
            "customer_price": "1250.50",
            "weight_kg": "7800",
            "adr_required": True,
        },
        raw_model_response='{"customer_name": "Acme Logistics"}',
        confidence_summary=None,
        normalization_warnings=[],
        provider="lm_studio",
        model_name="test-model",
    )

    async def mock_extract(_raw_text: str, _settings: object) -> ModelExtractionResult:
        return mock_result

    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.extract_load_order_with_model",
        mock_extract,
    )

    from app.backend.core.settings import Settings

    mock_settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///./tests.db",
        INGESTION_MODEL_NAME="test-model",
    )
    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.get_settings",
        lambda: mock_settings,
    )

    raw_text = "Customer: Acme Logistics\nOrigin: Madrid, ES"
    async with session_factory() as session:
        response = await ingest_load_order_from_raw_text(session, user.id, raw_text)
        await session.commit()

        run = await session.get(IngestionRun, response.ingestion_run_id)

    assert response.run_status == IngestionRunStatus.COMPLETED
    assert response.execution_path == "model"
    assert response.provider == "lm_studio"
    assert response.model_name == "test-model"
    assert response.trace_steps is not None
    assert len(response.trace_steps) > 0
    assert run is not None
    assert run.execution_path == "model"
    assert run.provider == "lm_studio"
    assert run.model_name == "test-model"
    assert run.trace_steps is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_falls_back_to_deterministic_when_model_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    async def mock_extract_fail(_raw_text: str, _settings: object) -> ModelExtractionResult:
        raise RuntimeError("model connection refused")

    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.extract_load_order_with_model",
        mock_extract_fail,
    )

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
Price: 1250.50
Weight: 7800
""".strip()

    async with session_factory() as session:
        response = await ingest_load_order_from_raw_text(session, user.id, raw_text)
        await session.commit()

        run = await session.get(IngestionRun, response.ingestion_run_id)

    assert response.run_status == IngestionRunStatus.COMPLETED
    assert response.execution_path == "fallback"
    assert response.trace_steps is not None
    assert any(step["node"] == "model_extract" for step in response.trace_steps)
    assert any(step["node"] == "fallback" for step in response.trace_steps)
    assert run is not None
    assert run.execution_path == "fallback"
    assert run.trace_steps is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_discards_invalid_model_fields_without_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    mock_result = ModelExtractionResult(
        extracted_payload={
            "customer_name": "ElectroHispana S.L.",
            "origin_text": "Valencia, ES",
            "destination_text": "Frankfurt, DE",
            "origin_load_date": "tomorrow morning",
            "cargo_description": "10 palets americanos con bobinas de cableado industrial.",
            "customer_price": "2400 EUR",
        },
        raw_model_response='{"customer_name": "ElectroHispana S.L."}',
        confidence_summary=None,
        normalization_warnings=[],
        provider="lm_studio",
        model_name="test-model",
    )

    async def mock_extract(_raw_text: str, _settings: object) -> ModelExtractionResult:
        return mock_result

    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.extract_load_order_with_model",
        mock_extract,
    )

    from app.backend.core.settings import Settings

    mock_settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///./tests.db",
        INGESTION_MODEL_NAME="test-model",
    )
    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.get_settings",
        lambda: mock_settings,
    )

    raw_text = """
Buenas tardes,
Origen: Valencia, ES
Destino: Frankfurt, DE
Descripcion de la carga: 10 palets americanos con bobinas de cableado industrial.
Nuestro presupuesto cerrado para este envio es de 2400 EUR.
""".strip()

    async with session_factory() as session:
        response = await ingest_load_order_from_raw_text(session, user.id, raw_text)
        await session.commit()

        run = await session.get(IngestionRun, response.ingestion_run_id)

    assert response.run_status == IngestionRunStatus.COMPLETED
    assert response.load_order.customer_name == "ElectroHispana S.L."
    assert response.load_order.origin_text == "Valencia, ES"
    assert response.load_order.destination_text == "Frankfurt, DE"
    assert response.load_order.customer_price is not None
    assert response.load_order.origin_load_date is None
    assert run is not None
    assert run.status == IngestionRunStatus.COMPLETED
    assert run.normalization_warnings is not None
    assert "discarded_ungrounded_model_field:origin_load_date" in run.normalization_warnings

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_normalizes_timezone_aware_model_datetime_for_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    mock_result = ModelExtractionResult(
        extracted_payload={
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "origin_load_date": "2026-05-04T09:30:00Z",
            "cargo_description": "Ceramic tiles",
        },
        raw_model_response='{"origin_load_date": "2026-05-04T09:30:00Z"}',
        confidence_summary=None,
        normalization_warnings=[],
        provider="lm_studio",
        model_name="test-model",
    )

    async def mock_extract(_raw_text: str, _settings: object) -> ModelExtractionResult:
        return mock_result

    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.extract_load_order_with_model",
        mock_extract,
    )

    from app.backend.core.settings import Settings

    mock_settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///./tests.db",
        INGESTION_MODEL_NAME="test-model",
    )
    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.get_settings",
        lambda: mock_settings,
    )

    raw_text = """
Customer: Acme Logistics
Origin: Madrid, ES
Destination: Paris, FR
Load Date: 2026-05-04 09:30
Cargo: Ceramic tiles
""".strip()

    async with session_factory() as session:
        response = await ingest_load_order_from_raw_text(session, user.id, raw_text)
        await session.commit()

        load_order = await session.get(LoadOrder, response.load_order.id)

    assert load_order is not None
    assert load_order.origin_load_date is not None
    assert load_order.origin_load_date.tzinfo is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_load_order_prefers_inferred_company_and_textual_truck_type_from_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    mock_result = ModelExtractionResult(
        extracted_payload={
            "customer_name": "Carmen Ortiz",
            "origin_text": "Sevilla, ES",
            "destination_text": "Rotterdam, NL",
            "origin_load_date": "2026-05-04T09:30:00",
            "cargo_description": "Palets de producto químico de limpieza",
            "truck_type_id": "tautliner",
        },
        raw_model_response='{"customer_name": "Carmen Ortiz", "truck_type_id": "tautliner"}',
        confidence_summary=None,
        normalization_warnings=[],
        provider="lm_studio",
        model_name="test-model",
    )

    async def mock_extract(_raw_text: str, _settings: object) -> ModelExtractionResult:
        return mock_result

    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.extract_load_order_with_model",
        mock_extract,
    )

    from app.backend.core.settings import Settings

    mock_settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///./tests.db",
        INGESTION_MODEL_NAME="test-model",
    )
    monkeypatch.setattr(
        "app.backend.services.load_order_ingestion.get_settings",
        lambda: mock_settings,
    )

    raw_text = """
Hola, equipo:

Origen: Sevilla, ES
Destino: Rotterdam, NL
Fecha de carga: 2026-05-04 09:30
Descripcion de la carga: Palets de producto químico de limpieza
Tipo de camión: tautliner

Saludos cordiales,
Carmen Ortiz
Export Manager | SurQuimica Global S.L.
""".strip()

    async with session_factory() as session:
        response = await ingest_load_order_from_raw_text(session, user.id, raw_text)
        await session.commit()

    assert response.load_order.customer_name == "SurQuimica Global S.L."
    assert response.load_order.truck_type_id == 1

    await engine.dispose()
