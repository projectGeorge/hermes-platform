"""Unit tests for the monitoring agent rule engine."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backend.core.domain_enums import (
    LoadOrderStatus,
    MonitoringAlertSeverity,
    MonitoringAlertStatus,
    MonitoringAlertType,
    TripProposalStatus,
)
from app.backend.db.base import Base
from app.backend.models.load_order import LoadOrder
from app.backend.models.monitoring_alert import MonitoringAlert
from app.backend.models.execution_monitoring_snapshot import ExecutionMonitoringSnapshot
from app.backend.models.user import User
from app.backend.services.monitoring_agent import (
    evaluate_order_alerts,
    get_open_alerts,
    refresh_active_orders_alerts,
)
from app.backend.services.execution_monitoring import ensure_execution_monitoring_snapshot
from app.backend.models.carrier import Carrier
from app.backend.models.trip import Trip
from decimal import Decimal

from app.backend.services.execution_monitoring import refresh_execution_monitoring_snapshot


def test_maptiler_coordinate_from_features_prefers_matching_country() -> None:
    from app.backend.services.execution_monitoring import _maptiler_coordinate_from_features

    features = [
        {
            "center": [-100.3161, 25.6714],
            "properties": {"country_code": "MX"},
        },
        {
            "center": [4.4777, 51.9244],
            "properties": {"country_code": "NL"},
        },
    ]

    coordinate = _maptiler_coordinate_from_features(features, expected_country_code="NL")

    assert coordinate == {"lat": 51.9244, "lng": 4.4777}


def test_maptiler_coordinate_from_features_rejects_country_mismatch() -> None:
    from app.backend.services.execution_monitoring import _maptiler_coordinate_from_features

    features = [
        {
            "center": [-100.3161, 25.6714],
            "properties": {"country_code": "MX"},
        }
    ]

    with pytest.raises(IndexError):
        _maptiler_coordinate_from_features(features, expected_country_code="NL")


@pytest_asyncio.fixture
async def engine():
    return create_async_engine("sqlite+aiosqlite:///:memory:", future=True)


@pytest_asyncio.fixture
async def session_factory(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_missing_route_data_alert(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            origin_text=None,
            destination_text=None,
        )
        session.add_all([user, order])
        await session.flush()

        alerts = await evaluate_order_alerts(session, order)
        await session.commit()

        missing_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.MISSING_ROUTE_DATA]
        assert len(missing_alerts) == 1
        assert missing_alerts[0].severity == MonitoringAlertSeverity.WARNING
        assert missing_alerts[0].status == MonitoringAlertStatus.OPEN


@pytest.mark.asyncio
async def test_no_missing_route_data_when_complete(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.FORMALIZED,
            currency="EUR",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
        )
        session.add_all([user, order])
        await session.flush()

        alerts = await evaluate_order_alerts(session, order)
        await session.commit()

        missing_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.MISSING_ROUTE_DATA]
        assert len(missing_alerts) == 0


@pytest.mark.asyncio
async def test_deadline_approaching_alert(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
            origin_load_date=datetime.now() + timedelta(hours=12),
        )
        session.add_all([user, order])
        await session.flush()

        alerts = await evaluate_order_alerts(session, order)
        await session.commit()

        deadline_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.DEADLINE_APPROACHING]
        assert len(deadline_alerts) == 1
        assert deadline_alerts[0].severity == MonitoringAlertSeverity.WARNING


@pytest.mark.asyncio
async def test_no_deadline_alert_when_far_out(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
            origin_load_date=datetime.now() + timedelta(days=7),
        )
        session.add_all([user, order])
        await session.flush()

        alerts = await evaluate_order_alerts(session, order)
        await session.commit()

        deadline_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.DEADLINE_APPROACHING]
        assert len(deadline_alerts) == 0


@pytest.mark.asyncio
async def test_stalled_workflow_alert(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.PENDING_INGESTION,
            currency="EUR",
            created_at=datetime.now() - timedelta(hours=25),
        )
        session.add_all([user, order])
        await session.flush()

        alerts = await evaluate_order_alerts(session, order)
        await session.commit()

        stalled_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.STALLED_WORKFLOW]
        assert len(stalled_alerts) == 1


@pytest.mark.asyncio
async def test_no_stalled_alert_for_recent_order(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.PENDING_INGESTION,
            currency="EUR",
            created_at=datetime.now() - timedelta(hours=1),
        )
        session.add_all([user, order])
        await session.flush()

        alerts = await evaluate_order_alerts(session, order)
        await session.commit()

        stalled_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.STALLED_WORKFLOW]
        assert len(stalled_alerts) == 0


@pytest.mark.asyncio
async def test_alert_deduplication(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            origin_text=None,
            destination_text=None,
        )
        session.add_all([user, order])
        await session.flush()

        alerts1 = await evaluate_order_alerts(session, order)
        await session.commit()

    async with session_factory() as session:
        order_ref = await session.get(LoadOrder, order.id)
        assert order_ref is not None
        alerts2 = await evaluate_order_alerts(session, order_ref)
        await session.commit()

        from app.backend.models.monitoring_alert import MonitoringAlert
        from sqlalchemy import select
        result = await session.execute(
            select(MonitoringAlert).where(
                MonitoringAlert.alert_type == MonitoringAlertType.MISSING_ROUTE_DATA,
                MonitoringAlert.load_order_id == order.id,
            )
        )
        all_missing = list(result.scalars().all())
        open_missing = [a for a in all_missing if a.status == MonitoringAlertStatus.OPEN]
        assert len(open_missing) == 1


@pytest.mark.asyncio
async def test_get_open_alerts_returns_recent(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            origin_text=None,
            destination_text=None,
        )
        session.add_all([user, order])
        await session.flush()
        await evaluate_order_alerts(session, order)
        await session.commit()

    async with session_factory() as session:
        alerts = await get_open_alerts(session)
        assert len(alerts) >= 1
        assert all(a.status == MonitoringAlertStatus.OPEN for a in alerts)


@pytest.mark.asyncio
async def test_ensure_execution_monitoring_snapshot_creates_persisted_read_model(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.FORMALIZED,
            currency="EUR",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
        )
        session.add_all([user, order])
        await session.flush()

        snapshot = await ensure_execution_monitoring_snapshot(session, order, source="unit_test")
        await session.commit()

        assert snapshot.load_order_id == order.id
        assert snapshot.current_checkpoint == "Madrid, ES"
        assert snapshot.route_points[0]["label"] == "Madrid, ES"
        assert snapshot.route_points[-1]["label"] == "Paris, FR"
        assert len(snapshot.route_points) == 4
        assert snapshot.events[0]["event_type"] == "monitoring_initialized"
        assert snapshot.extra_metadata is not None
        assert snapshot.extra_metadata["route_path"]
        assert snapshot.extra_metadata["current_position"]["label"] == "Madrid, ES"
        assert snapshot.extra_metadata["route_geometry_version"] == 2
        assert snapshot.extra_metadata["route_geometry_source"] in {"fallback_interpolation", "openrouteservice"}
        assert snapshot.extra_metadata["origin_coordinate"]
        assert snapshot.extra_metadata["destination_coordinate"]

        result = await session.execute(select(ExecutionMonitoringSnapshot))
        stored = result.scalar_one()
        assert stored.extra_metadata["initialization_source"] == "unit_test"


@pytest.mark.asyncio
async def test_refresh_execution_monitoring_snapshot_persists_progress_and_events(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.FORMALIZED,
            currency="EUR",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
            distance_km=Decimal("1270.00"),
            cargo_description="Ceramic tiles",
        )
        session.add_all([user, order])
        await session.flush()

        await ensure_execution_monitoring_snapshot(session, order, source="unit_test")
        snapshot = await refresh_execution_monitoring_snapshot(
            session,
            order,
            source="unit_test_refresh",
        )
        await session.commit()

        assert snapshot.progress_percent > 0
        assert snapshot.status.value in {"in_transit", "delayed", "delivered"}
        assert len(snapshot.events) >= 2
        assert snapshot.events[-1]["event_type"] != "monitoring_initialized"
        assert snapshot.alerts == [] or all(alert["status"] == "open" for alert in snapshot.alerts)
        assert snapshot.extra_metadata is not None
        assert snapshot.extra_metadata["current_position"]["progress_percent"] == snapshot.progress_percent
        assert snapshot.extra_metadata["last_refresh_source"] == "unit_test_refresh"
        assert snapshot.extra_metadata["route_path"][0]["lat"] == snapshot.route_points[0]["lat"]
        assert snapshot.extra_metadata["route_path"][-1]["lng"] == snapshot.route_points[-1]["lng"]


@pytest.mark.asyncio
async def test_refresh_execution_monitoring_snapshot_can_enrich_agent_update_with_cloud_reasoning(session_factory) -> None:
    from app.backend.core.settings import Settings
    from app.backend.services.model_runtime_gateway import CompletionResult, RuntimeProvenance

    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.FORMALIZED,
            currency="EUR",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
            distance_km=Decimal("1270.00"),
            cargo_description="Ceramic tiles",
        )
        session.add_all([user, order])
        await session.flush()

        await ensure_execution_monitoring_snapshot(session, order, source="unit_test")

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )
        mock_result = AsyncMock()
        mock_result.content = {
            "summary": "Shipment passed the outbound linehaul checkpoint and remains on schedule.",
            "incident_summary": None,
            "operator_note": "No action needed. Check again near the final leg.",
        }

        with patch(
            "app.backend.core.settings.get_settings",
            return_value=settings,
        ):
            with patch(
                "app.backend.services.model_runtime_gateway.structured_completion",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                snapshot = await refresh_execution_monitoring_snapshot(
                    session,
                    order,
                    source="unit_test_cloud_refresh",
                    allow_cloud_reasoning=True,
                )
                await session.commit()

        assert snapshot.extra_metadata is not None
        assert snapshot.extra_metadata["agent_update"]["source"] == "cloud"
        assert "outbound linehaul" in snapshot.extra_metadata["agent_update"]["summary"].lower()


@pytest.mark.asyncio
async def test_refresh_execution_monitoring_snapshot_can_create_bounded_ai_incident(session_factory) -> None:
    from app.backend.core.settings import Settings

    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.FORMALIZED,
            currency="EUR",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
            distance_km=Decimal("1270.00"),
            cargo_description="Ceramic tiles",
        )
        session.add_all([user, order])
        await session.flush()

        await ensure_execution_monitoring_snapshot(session, order, source="unit_test")
        await refresh_execution_monitoring_snapshot(
            session,
            order,
            source="unit_test_seed_progress",
            allow_cloud_reasoning=False,
        )

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )
        mock_result = AsyncMock()
        mock_result.content = {
            "should_create": True,
            "event_type": "border_delay_detected",
            "severity": "warning",
            "title": "Border queue building",
            "detail": "Customs processing is temporarily slower than the route baseline.",
            "checkpoint_name": "ES/FR border",
            "operator_note": "Keep the consignee informed if the delay persists on the next refresh.",
        }

        with patch(
            "app.backend.services.execution_monitoring.get_settings",
            return_value=settings,
        ):
            with patch(
                "app.backend.services.model_runtime_gateway.structured_completion",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                snapshot = await refresh_execution_monitoring_snapshot(
                    session,
                    order,
                    source="unit_test_ai_incident",
                    allow_cloud_reasoning=True,
                )
                await session.commit()

        assert any(event["title"] == "Border queue building" for event in snapshot.events)
        assert any(alert["title"] == "Border queue building" for alert in snapshot.alerts)
        assert snapshot.extra_metadata is not None
        assert any(
            alert.get("metadata", {}).get("source") == "ai_monitoring_incident"
            for alert in snapshot.alerts
        )


@pytest.mark.asyncio
async def test_refresh_execution_monitoring_snapshot_falls_back_when_ai_incident_is_invalid(session_factory) -> None:
    from app.backend.core.settings import Settings

    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.FORMALIZED,
            currency="EUR",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
            distance_km=Decimal("1270.00"),
            cargo_description="Ceramic tiles",
        )
        session.add_all([user, order])
        await session.flush()

        await ensure_execution_monitoring_snapshot(session, order, source="unit_test")
        await refresh_execution_monitoring_snapshot(
            session,
            order,
            source="unit_test_seed_progress",
            allow_cloud_reasoning=False,
        )

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )
        mock_result = AsyncMock()
        mock_result.content = {
            "should_create": True,
            "event_type": "invented_incident_type",
            "severity": "warning",
            "title": "Bad output",
            "detail": "This should not persist.",
            "checkpoint_name": "ES/FR border",
            "operator_note": None,
        }

        with patch(
            "app.backend.core.settings.get_settings",
            return_value=settings,
        ):
            with patch(
                "app.backend.services.model_runtime_gateway.structured_completion",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                snapshot = await refresh_execution_monitoring_snapshot(
                    session,
                    order,
                    source="unit_test_ai_invalid",
                    allow_cloud_reasoning=True,
                )
                await session.commit()

        assert all(event["event_type"] != "invented_incident_type" for event in snapshot.events)
        assert all(alert["title"] != "Bad output" for alert in snapshot.alerts)
        assert any(event["event_type"] in {"border_delay_detected", "unplanned_stop"} for event in snapshot.events)


@pytest.mark.asyncio
async def test_refresh_execution_monitoring_snapshot_bounds_ai_incident_count(session_factory) -> None:
    from app.backend.core.settings import Settings

    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.FORMALIZED,
            currency="EUR",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
            distance_km=Decimal("1270.00"),
            cargo_description="Ceramic tiles",
        )
        session.add_all([user, order])
        await session.flush()

        await ensure_execution_monitoring_snapshot(session, order, source="unit_test")
        await refresh_execution_monitoring_snapshot(
            session,
            order,
            source="unit_test_seed_progress",
            allow_cloud_reasoning=False,
        )

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )

        incident_responses = [
            {
                "should_create": True,
                "event_type": "border_delay_detected",
                "severity": "warning",
                "title": "Border delay detected",
                "detail": "Delay signal one.",
                "checkpoint_name": "ES/FR border",
                "operator_note": None,
            },
            {
                "should_create": True,
                "event_type": "unplanned_stop",
                "severity": "warning",
                "title": "Unplanned stop detected",
                "detail": "Delay signal two.",
                "checkpoint_name": "Linehaul corridor",
                "operator_note": None,
            },
            {
                "should_create": True,
                "event_type": "on_time_recovery",
                "severity": "info",
                "title": "On-time recovery",
                "detail": "Delay signal three.",
                "checkpoint_name": "Linehaul corridor",
                "operator_note": None,
            },
        ]

        async def fake_structured_completion(*, settings, messages, profile):
            system_prompt = messages[0]["content"]
            if "monitoring incident generator" in system_prompt:
                payload = incident_responses.pop(0)
            else:
                payload = {
                    "summary": "Shipment update generated for monitoring summary.",
                    "incident_summary": None,
                    "operator_note": None,
                }

            return CompletionResult(
                content=payload,
                provenance=RuntimeProvenance(
                    provider="openrouter",
                    model_name="deepseek/deepseek-flash-v1",
                    runtime_profile=profile,
                ),
                raw_text="{}",
            )

        with patch(
            "app.backend.core.settings.get_settings",
            return_value=settings,
        ):
            with patch(
                "app.backend.services.model_runtime_gateway.structured_completion",
                new=fake_structured_completion,
            ):
                for refresh_index in range(4):
                    snapshot = await refresh_execution_monitoring_snapshot(
                        session,
                        order,
                        source=f"unit_test_ai_bound_{refresh_index}",
                        allow_cloud_reasoning=True,
                    )
                await session.commit()

        ai_event_titles = {
            event["title"]
            for event in snapshot.events
            if event["title"] in {"Border delay detected", "Unplanned stop detected", "On-time recovery"}
        }
        assert len(ai_event_titles) >= 1
        assert len(ai_event_titles) <= 2


@pytest.mark.asyncio
async def test_margin_risk_opens_when_below_threshold(session_factory) -> None:
    """margin_risk opens when trip margin is below 10% of customer_price."""
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            customer_price=Decimal("1000.00"),
        )
        carrier = Carrier(company_name="Test Carrier")
        trip = Trip(
            load_order=order,
            carrier=carrier,
            profit_margin=Decimal("50.00"),
            carrier_price=Decimal("950.00"),
            proposal_status=TripProposalStatus.CANDIDATE.value,
        )
        session.add_all([user, order, carrier, trip])
        await session.flush()

        alerts = await evaluate_order_alerts(session, order)
        await session.commit()

        margin_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.MARGIN_RISK]
        assert len(margin_alerts) == 1
        assert margin_alerts[0].severity == MonitoringAlertSeverity.WARNING


@pytest.mark.asyncio
async def test_margin_risk_resolves_when_above_threshold(session_factory) -> None:
    """margin_risk resolves when margin rises above 10% of customer_price."""
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            customer_price=Decimal("1000.00"),
        )
        carrier = Carrier(company_name="Better Carrier")
        trip = Trip(
            load_order=order,
            carrier=carrier,
            profit_margin=Decimal("200.00"),
            carrier_price=Decimal("800.00"),
            proposal_status=TripProposalStatus.CANDIDATE.value,
        )
        session.add_all([user, order, carrier, trip])
        await session.flush()

        alerts = await evaluate_order_alerts(session, order)
        await session.commit()

        margin_alerts = [a for a in alerts if a.alert_type == MonitoringAlertType.MARGIN_RISK]
        assert len(margin_alerts) == 0

        open_margin = await session.execute(
            select(MonitoringAlert).where(
                MonitoringAlert.alert_type == MonitoringAlertType.MARGIN_RISK,
                MonitoringAlert.load_order_id == order.id,
                MonitoringAlert.status == MonitoringAlertStatus.OPEN,
            )
        )
        assert len(list(open_margin.scalars().all())) == 0


@pytest.mark.asyncio
async def test_missing_route_data_resolves_when_filled(session_factory) -> None:
    """missing_route_data resolves when origin and destination are provided."""
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            origin_text=None,
            destination_text=None,
        )
        session.add_all([user, order])
        await session.flush()
        await evaluate_order_alerts(session, order)
        await session.commit()

    async with session_factory() as session:
        order_ref = await session.get(LoadOrder, order.id)
        order_ref.origin_text = "Madrid"
        order_ref.destination_text = "Paris"
        await evaluate_order_alerts(session, order_ref)
        await session.commit()

        open_missing = await session.execute(
            select(MonitoringAlert).where(
                MonitoringAlert.alert_type == MonitoringAlertType.MISSING_ROUTE_DATA,
                MonitoringAlert.load_order_id == order.id,
                MonitoringAlert.status == MonitoringAlertStatus.OPEN,
            )
        )
        assert len(list(open_missing.scalars().all())) == 0


@pytest.mark.asyncio
async def test_refresh_active_orders_alerts(session_factory) -> None:
    """refresh_active_orders_alerts re-evaluates all non-cancelled orders."""
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            origin_text=None,
            destination_text=None,
        )
        session.add_all([user, order])
        await session.flush()
        await evaluate_order_alerts(session, order)
        await session.commit()

    async with session_factory() as session:
        await refresh_active_orders_alerts(session)
        await session.commit()

        alerts = await get_open_alerts(session)
        missing = [a for a in alerts if a.alert_type == MonitoringAlertType.MISSING_ROUTE_DATA]
        assert len(missing) >= 1


class TestCloudMonitoringEvaluation:
    def test_monitoring_alert_schema_validation(self) -> None:
        from app.backend.services.monitoring_agent import (
            ModelMonitoringAlert,
            _validate_monitoring_alert,
        )

        valid = {
            "should_open": True,
            "alert_type": "deadline_approaching",
            "severity": "warning",
            "title": "Deadline approaching",
            "detail": "Pickup in 12h.",
            "suggested_action": "Prioritize this order.",
        }

        result = _validate_monitoring_alert(valid)
        assert isinstance(result, ModelMonitoringAlert)
        assert result.should_open is True
        assert result.alert_type == "deadline_approaching"
        assert result.severity == "warning"

    def test_monitoring_alert_fallback_on_invalid(self) -> None:
        from app.backend.services.monitoring_agent import (
            ModelMonitoringAlert,
            _validate_monitoring_alert,
        )

        result = _validate_monitoring_alert({"bad": "shape"})
        assert isinstance(result, ModelMonitoringAlert)
        assert result.should_open is False
        assert "fallback" in result.detail.lower()

    @pytest.mark.asyncio
    async def test_generate_cloud_alert_uses_reasoning_profile(self) -> None:
        from app.backend.services.monitoring_agent import (
            ModelMonitoringAlert,
            _generate_cloud_alert,
        )
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )

        model_output = {
            "should_open": True,
            "alert_type": "stalled_workflow",
            "severity": "warning",
            "title": "Workflow stalled",
            "detail": "Order stalled for 25h.",
            "suggested_action": "Escalate to operator.",
        }

        mock_result = AsyncMock()
        mock_result.content = model_output

        with patch(
            "app.backend.services.model_runtime_gateway.structured_completion",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_completion:
            alert = await _generate_cloud_alert(
                settings=settings,
                order_summary="Order in pending_ingestion for 25h",
            )

        assert isinstance(alert, ModelMonitoringAlert)
        assert alert.should_open is True
        assert alert.alert_type == "stalled_workflow"

        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["profile"] == "reasoning"
        assert call_kwargs["settings"] == settings

    @pytest.mark.asyncio
    async def test_generate_cloud_alert_fallback_on_error(self) -> None:
        from app.backend.services.monitoring_agent import (
            ModelMonitoringAlert,
            _generate_cloud_alert,
        )
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )

        with patch(
            "app.backend.services.model_runtime_gateway.structured_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Model down"),
        ):
            alert = await _generate_cloud_alert(
                settings=settings,
                order_summary="Test order",
            )

        assert isinstance(alert, ModelMonitoringAlert)
        assert alert.should_open is False
        assert "fallback" in alert.detail.lower()


@pytest.mark.asyncio
async def test_valid_cloud_monitoring_result_replaces_deterministic_rules(session_factory) -> None:
    from app.backend.core.settings import Settings

    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            origin_text=None,
            destination_text=None,
        )
        session.add_all([user, order])
        await session.flush()

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )
        mock_result = AsyncMock()
        mock_result.content = {
            "should_open": False,
            "alert_type": "",
            "severity": "info",
            "title": "No alert",
            "detail": "No operational concern detected.",
            "suggested_action": None,
        }

        with patch(
            "app.backend.core.settings.get_settings",
            return_value=settings,
        ):
            with patch(
                "app.backend.services.model_runtime_gateway.structured_completion",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                alerts = await evaluate_order_alerts(session, order, allow_cloud_reasoning=True)
                await session.commit()

        assert alerts == []

        persisted = await session.execute(select(MonitoringAlert))
        assert list(persisted.scalars().all()) == []


@pytest.mark.asyncio
async def test_cloud_monitoring_fallback_tags_deterministic_alerts(session_factory) -> None:
    from app.backend.core.settings import Settings

    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_CONFIRMED,
            currency="EUR",
            origin_text=None,
            destination_text=None,
        )
        session.add_all([user, order])
        await session.flush()

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )

        with patch(
            "app.backend.core.settings.get_settings",
            return_value=settings,
        ):
            with patch(
                "app.backend.services.model_runtime_gateway.structured_completion",
                new_callable=AsyncMock,
                side_effect=RuntimeError("model down"),
            ):
                alerts = await evaluate_order_alerts(session, order, allow_cloud_reasoning=True)
                await session.commit()

        assert len(alerts) >= 1
        assert all(alert.extra_metadata is not None for alert in alerts)
        assert all(alert.extra_metadata["execution_path"] == "fallback" for alert in alerts)
        assert all(str(alert.dedupe_key).startswith("fallback:") for alert in alerts)
