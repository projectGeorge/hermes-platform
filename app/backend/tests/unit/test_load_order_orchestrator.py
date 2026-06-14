"""Unit tests for the orchestrator decision service."""
from unittest.mock import AsyncMock, patch

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backend.core.domain_enums import (
    AgentActivityState,
    AgentKind,
    LoadOrderStatus,
    SmartCommsContextType,
)
from app.backend.db.base import Base
from app.backend.models.user import User
from app.backend.models.load_order import LoadOrder
from app.backend.services.load_order_orchestrator import (
    log_order_created,
    log_ingestion_completed,
    log_viability_confirmed,
    log_carrier_search_completed,
    log_carrier_selected,
    log_order_cancelled,
    log_order_formalized,
    log_orchestrator_manual_refresh,
)
from app.backend.services.delegated_orchestrator import _maybe_handoff_to_smart_comms
from app.backend.services.runtime_settings import invalidate_boolean_settings_cache, upsert_runtime_settings
from app.backend.schemas.settings import RuntimeSettingsUpdate
from app.backend.services.smart_comms_service import get_conversation_messages


@pytest_asyncio.fixture
async def engine():
    return create_async_engine("sqlite+aiosqlite:///:memory:", future=True)


@pytest_asyncio.fixture
async def session_factory(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_log_order_created_creates_activity(session_factory) -> None:
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
            customer_name="Acme Corp",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
        )
        session.add_all([user, order])
        await session.flush()

        activity = await log_order_created(session, order)
        await session.commit()

        assert activity.agent_kind == AgentKind.ORCHESTRATOR
        assert activity.activity_state == AgentActivityState.COMPLETED
        assert activity.activity_key == "order_created"
        assert "Acme Corp" in activity.title


@pytest.mark.asyncio
async def test_log_ingestion_completed_creates_activity(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_PENDING,
            currency="EUR",
        )
        session.add_all([user, order])
        await session.flush()

        activity = await log_ingestion_completed(session, order)
        await session.commit()

        assert activity.agent_kind == AgentKind.ORCHESTRATOR
        assert activity.activity_key == "ingestion_completed"
        assert activity.load_order_id == order.id


@pytest.mark.asyncio
async def test_log_ingestion_completed_uses_model_decision_for_next_action(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_PENDING,
            currency="EUR",
        )
        session.add_all([user, order])
        await session.flush()

        mock_result = AsyncMock()
        mock_result.content = {
            "workflow_interpretation": "ingestion_complete",
            "next_action": "await_operator_review",
            "action_owner": "operator",
            "explanation": "Operator should review the extracted data.",
        }

        with patch(
            "app.backend.services.model_runtime_gateway.structured_completion",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            with patch(
                "app.backend.services.load_order_orchestrator.get_settings",
                return_value=type("StubSettings", (), {
                    "reasoning_model_name": "deepseek/test",
                    "reasoning_model_provider": "openrouter",
                })(),
            ):
                activity = await log_ingestion_completed(session, order)

        assert activity.activity_state == AgentActivityState.AWAITING_OPERATOR
        assert activity.detail == "Operator should review the extracted data."
        assert activity.next_action == "Await operator review"
        assert activity.extra_metadata is not None
        assert activity.extra_metadata["execution_path"] == "cloud"


@pytest.mark.asyncio
async def test_log_carrier_search_completed_uses_fast_default_metadata(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.SEARCHING_CARRIER,
            currency="EUR",
        )
        session.add_all([user, order])
        await session.flush()

        activity = await log_carrier_search_completed(session, order, candidate_count=3)

        assert activity.activity_state == AgentActivityState.AWAITING_OPERATOR
        assert activity.detail == "Found and ranked 3 carrier candidates."
        assert activity.next_action == "Operator selects carrier"
        assert activity.extra_metadata is None


@pytest.mark.asyncio
async def test_log_orchestrator_manual_refresh_keeps_manual_context_on_fallback(
    session_factory,
) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.VIABILITY_PENDING,
            currency="EUR",
        )
        session.add_all([user, order])
        await session.flush()

        with patch(
            "app.backend.services.model_runtime_gateway.structured_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with patch(
                "app.backend.services.load_order_orchestrator.get_settings",
                return_value=type("StubSettings", (), {
                    "reasoning_model_name": "deepseek/test",
                    "reasoning_model_provider": "openrouter",
                })(),
            ):
                activity = await log_orchestrator_manual_refresh(session, order)

        assert activity.activity_key == "orchestrator_manual_refresh"
        assert activity.detail is not None
        assert "Manual refresh evaluated current workflow state" in activity.detail
        assert activity.extra_metadata is not None
        assert activity.extra_metadata["execution_path"] == "fallback"


@pytest.mark.asyncio
async def test_log_viability_confirmed_creates_awaiting_operator_state(session_factory) -> None:
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
        )
        session.add_all([user, order])
        await session.flush()

        activity = await log_viability_confirmed(session, order)
        await session.commit()

        assert activity.agent_kind == AgentKind.ORCHESTRATOR
        assert activity.activity_state == AgentActivityState.COMPLETED
        assert activity.activity_key == "viability_confirmed"


@pytest.mark.asyncio
async def test_log_carrier_search_completed_creates_activity(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.SEARCHING_CARRIER,
            currency="EUR",
        )
        session.add_all([user, order])
        await session.flush()

        activity = await log_carrier_search_completed(session, order, candidate_count=15)
        await session.commit()

        assert activity.agent_kind == AgentKind.ORCHESTRATOR
        assert activity.activity_key == "carrier_search_completed"
        assert "15" in activity.title


@pytest.mark.asyncio
async def test_log_carrier_selected_creates_activity(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.READY_FOR_FORMALIZATION,
            currency="EUR",
        )
        session.add_all([user, order])
        await session.flush()

        activity = await log_carrier_selected(session, order, carrier_name="Atlas Logistics")
        await session.commit()

        assert activity.agent_kind == AgentKind.ORCHESTRATOR
        assert activity.activity_key == "carrier_selected"
        assert "Atlas Logistics" in activity.title


@pytest.mark.asyncio
async def test_log_order_cancelled_creates_activity(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(
            user=user,
            status=LoadOrderStatus.CANCELLED,
            currency="EUR",
        )
        session.add_all([user, order])
        await session.flush()

        activity = await log_order_cancelled(session, order)
        await session.commit()

        assert activity.agent_kind == AgentKind.ORCHESTRATOR
        assert activity.activity_key == "order_cancelled"


class TestOrchestratorCloudDecision:
    @pytest.mark.asyncio
    async def test_generate_decision_uses_reasoning_profile(self) -> None:
        from app.backend.services.load_order_orchestrator import (
            OrchestratorDecision,
            generate_orchestrator_decision,
        )
        from app.backend.core.settings import Settings

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./tests.db",
            REASONING_MODEL_PROVIDER="openrouter",
            REASONING_MODEL_NAME="deepseek/deepseek-flash-v1",
            REASONING_MODEL_API_KEY="sk-test",
        )

        mock_result = AsyncMock()
        mock_result.content = {
            "workflow_interpretation": "order_received",
            "next_action": "run_ingestion",
            "action_owner": "agent",
            "explanation": "New order needs ingestion extraction.",
        }
        mock_result.provenance = AsyncMock()
        mock_result.provenance.provider = "openrouter"
        mock_result.provenance.model_name = "deepseek/deepseek-flash-v1"
        mock_result.provenance.runtime_profile = "reasoning"

        with patch(
            "app.backend.services.model_runtime_gateway.structured_completion",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_completion:
            decision = await generate_orchestrator_decision(
                settings=settings,
                order_status=LoadOrderStatus.PENDING_INGESTION,
            )

        assert isinstance(decision, OrchestratorDecision)
        assert decision.workflow_interpretation == "order_received"
        assert decision.next_action == "run_ingestion"
        assert decision.action_owner == "agent"

        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["profile"] == "reasoning"
        assert call_kwargs["settings"] == settings

    def test_invalid_decision_output_uses_fallback(self) -> None:
        from app.backend.services.load_order_orchestrator import (
            OrchestratorDecision,
            _validate_orchestrator_decision,
        )

        invalid = {
            "workflow_interpretation": "broken",
            "next_action": "dangerous_action",
        }

        result = _validate_orchestrator_decision(invalid)
        assert isinstance(result, OrchestratorDecision)
        assert result.next_action == "await_operator"
        assert result.action_owner == "operator"
        assert "fallback" in result.explanation.lower()

    def test_valid_decision_passes_validation(self) -> None:
        from app.backend.services.load_order_orchestrator import (
            OrchestratorDecision,
            _validate_orchestrator_decision,
        )

        valid = {
            "workflow_interpretation": "ingestion_complete",
            "next_action": "await_operator_review",
            "action_owner": "operator",
            "explanation": "Operator should review extracted data.",
        }

        result = _validate_orchestrator_decision(valid)
        assert isinstance(result, OrchestratorDecision)
        assert result.workflow_interpretation == "ingestion_complete"
        assert result.next_action == "await_operator_review"
        assert result.action_owner == "operator"

    def test_orchestrator_decision_schema(self) -> None:
        from app.backend.services.load_order_orchestrator import OrchestratorDecision

        decision = OrchestratorDecision(
            workflow_interpretation="carrier_search_required",
            next_action="run_carrier_search",
            action_owner="agent",
            explanation="Carrier search should start.",
        )

        assert decision.workflow_interpretation == "carrier_search_required"
        assert decision.next_action == "run_carrier_search"
        assert decision.action_owner == "agent"
        assert decision.explanation == "Carrier search should start."


# ─── Ingestion → Smart Comms handoff tests ────────────────────────────────────

class TestIngestionSmartCommsHandoff:
    @pytest.mark.asyncio
    async def test_handoff_creates_conversation_when_critical_missing(self, session_factory) -> None:
        invalidate_boolean_settings_cache()
        async with session_factory() as session:
            await upsert_runtime_settings(
                session,
                RuntimeSettingsUpdate(enable_ingestion_smart_comms_handoff=True),
            )
            user = User(
                id=uuid4(),
                email="test@example.com",
                operator_name="Test",
                auth_id="auth_test",
            )
            order = LoadOrder(
                id=uuid4(),
                user=user,
                status=LoadOrderStatus.PENDING_INGESTION,
                currency="EUR",
            )
            session.add_all([user, order])
            await session.flush()

            await _maybe_handoff_to_smart_comms(
                session,
                user_id=user.id,
                order_id=order.id,
                missing_fields={"customer_name": "not_found", "origin_text": "not_found"},
            )
            await session.commit()

        async with session_factory() as session:
            from app.backend.models.smart_comms_conversation import SmartCommsConversation
            from sqlalchemy import select

            stmt = select(SmartCommsConversation).where(
                SmartCommsConversation.context_id == order.id,
                SmartCommsConversation.user_id == user.id,
            )
            result = await session.execute(stmt)
            conv = result.scalar_one_or_none()
            assert conv is not None
            messages = await get_conversation_messages(session, conv.id)
            assert len(messages) == 1
            assert "customer and origin" in messages[0].content.lower()

    @pytest.mark.asyncio
    async def test_handoff_skips_when_no_critical_missing(self, session_factory) -> None:
        invalidate_boolean_settings_cache()
        async with session_factory() as session:
            await upsert_runtime_settings(
                session,
                RuntimeSettingsUpdate(enable_ingestion_smart_comms_handoff=True),
            )
            user = User(
                id=uuid4(),
                email="test@example.com",
                operator_name="Test",
                auth_id="auth_test",
            )
            order = LoadOrder(
                id=uuid4(),
                user=user,
                status=LoadOrderStatus.PENDING_INGESTION,
                currency="EUR",
            )
            session.add_all([user, order])
            await session.flush()

            await _maybe_handoff_to_smart_comms(
                session,
                user_id=user.id,
                order_id=order.id,
                missing_fields={"weight_kg": "not_found"},
            )
            await session.commit()

        async with session_factory() as session:
            from app.backend.models.smart_comms_conversation import SmartCommsConversation
            from sqlalchemy import select

            stmt = select(SmartCommsConversation).where(
                SmartCommsConversation.context_id == order.id,
                SmartCommsConversation.user_id == user.id,
            )
            result = await session.execute(stmt)
            conv = result.scalar_one_or_none()
            assert conv is None

    @pytest.mark.asyncio
    async def test_handoff_skips_when_settings_off(self, session_factory) -> None:
        invalidate_boolean_settings_cache()
        async with session_factory() as session:
            user = User(
                id=uuid4(),
                email="test@example.com",
                operator_name="Test",
                auth_id="auth_test",
            )
            order = LoadOrder(
                id=uuid4(),
                user=user,
                status=LoadOrderStatus.PENDING_INGESTION,
                currency="EUR",
            )
            session.add_all([user, order])
            await session.flush()

            from app.backend.services.runtime_settings import load_boolean_settings
            bool_settings = await load_boolean_settings(session)
            assert bool_settings.get("enable_ingestion_smart_comms_handoff") is False

            from app.backend.models.smart_comms_conversation import SmartCommsConversation
            from sqlalchemy import select

            stmt = select(SmartCommsConversation).where(
                SmartCommsConversation.context_id == order.id,
                SmartCommsConversation.user_id == user.id,
            )
            result = await session.execute(stmt)
            conv = result.scalar_one_or_none()
            assert conv is None

    @pytest.mark.asyncio
    async def test_handoff_logs_activity_events(self, session_factory) -> None:
        invalidate_boolean_settings_cache()
        async with session_factory() as session:
            await upsert_runtime_settings(
                session,
                RuntimeSettingsUpdate(enable_ingestion_smart_comms_handoff=True),
            )
            user = User(
                id=uuid4(),
                email="test@example.com",
                operator_name="Test",
                auth_id="auth_test",
            )
            order = LoadOrder(
                id=uuid4(),
                user=user,
                status=LoadOrderStatus.PENDING_INGESTION,
                currency="EUR",
            )
            session.add_all([user, order])
            await session.flush()

            await _maybe_handoff_to_smart_comms(
                session,
                user_id=user.id,
                order_id=order.id,
                missing_fields={"customer_name": "not_found", "origin_load_date": "not_found"},
            )
            await session.commit()

        async with session_factory() as session:
            from app.backend.models.agent_activity import AgentActivity
            from sqlalchemy import select

            stmt = select(AgentActivity).where(
                AgentActivity.load_order_id == order.id,
                AgentActivity.activity_key.in_(
                    ["ingestion_smart_comms_handoff", "smart_comms_clarification_prepared"]
                ),
            )
            result = await session.execute(stmt)
            activities = list(result.scalars().all())
            assert len(activities) == 2
            keys = {a.activity_key for a in activities}
            assert "ingestion_smart_comms_handoff" in keys
            assert "smart_comms_clarification_prepared" in keys

    @pytest.mark.asyncio
    async def test_handoff_message_mentions_exact_missing_field(self, session_factory) -> None:
        invalidate_boolean_settings_cache()
        async with session_factory() as session:
            await upsert_runtime_settings(
                session,
                RuntimeSettingsUpdate(enable_ingestion_smart_comms_handoff=True),
            )
            user = User(
                id=uuid4(),
                email="test@example.com",
                operator_name="Test",
                auth_id="auth_test",
            )
            order = LoadOrder(
                id=uuid4(),
                user=user,
                status=LoadOrderStatus.PENDING_INGESTION,
                currency="EUR",
            )
            session.add_all([user, order])
            await session.flush()

            await _maybe_handoff_to_smart_comms(
                session,
                user_id=user.id,
                order_id=order.id,
                missing_fields={"origin_load_date": "not_found"},
            )
            await session.commit()

        async with session_factory() as session:
            from app.backend.models.smart_comms_conversation import SmartCommsConversation
            from sqlalchemy import select

            stmt = select(SmartCommsConversation).where(
                SmartCommsConversation.context_id == order.id,
                SmartCommsConversation.user_id == user.id,
            )
            result = await session.execute(stmt)
            conv = result.scalar_one_or_none()
            assert conv is not None
            messages = await get_conversation_messages(session, conv.id)
            assert len(messages) == 1
            assert "load date" in messages[0].content.lower()
            assert "origin, destination" not in messages[0].content.lower()


# ─── Auto carrier search tests ───────────────────────────────────────────────

class TestAutoCarrierSearch:
    @pytest.mark.asyncio
    async def test_log_auto_carrier_search_triggered_creates_activity(self, session_factory) -> None:
        from app.backend.services.load_order_orchestrator import log_auto_carrier_search_triggered

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
                distance_km=1000,
                customer_price=1400,
            )
            session.add_all([user, order])
            await session.flush()

            activity = await log_auto_carrier_search_triggered(session, order)
            await session.commit()

            assert activity.agent_kind == AgentKind.ORCHESTRATOR
            assert activity.activity_key == "auto_carrier_search_triggered"
            assert activity.activity_state == AgentActivityState.COMPLETED
            assert "auto" in activity.title.lower()
