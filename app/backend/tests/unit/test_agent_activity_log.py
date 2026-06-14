"""Unit tests for the agent activity log service."""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backend.core.domain_enums import AgentActivityState, AgentKind, LoadOrderStatus
from app.backend.db.base import Base
from app.backend.models.user import User
from app.backend.models.load_order import LoadOrder
from app.backend.services.agent_activity_log import (
    append_agent_activity,
    get_agent_statuses,
    get_orchestrator_timeline,
)


@pytest_asyncio.fixture
async def engine():
    return create_async_engine("sqlite+aiosqlite:///:memory:", future=True)


@pytest_asyncio.fixture
async def session_factory(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_append_agent_activity_creates_row(session_factory) -> None:
    async with session_factory() as session:
        activity = await append_agent_activity(
            session,
            agent_kind=AgentKind.ORCHESTRATOR,
            activity_state=AgentActivityState.COMPLETED,
            title="Order received",
            activity_key="order_received",
        )
        await session.commit()

        assert activity.id is not None
        assert activity.agent_kind == AgentKind.ORCHESTRATOR
        assert activity.activity_state == AgentActivityState.COMPLETED
        assert activity.title == "Order received"
        assert activity.activity_key == "order_received"
        assert activity.created_at is not None


@pytest.mark.asyncio
async def test_append_agent_activity_with_load_order(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        order = LoadOrder(user=user, status=LoadOrderStatus.PENDING_INGESTION, currency="EUR")
        session.add_all([user, order])
        await session.flush()

        activity = await append_agent_activity(
            session,
            agent_kind=AgentKind.INGESTION,
            activity_state=AgentActivityState.COMPLETED,
            title="Extraction completed",
            activity_key="extraction_completed",
            load_order_id=order.id,
        )
        await session.commit()

        assert activity.load_order_id == order.id


@pytest.mark.asyncio
async def test_get_agent_statuses_returns_all_agents(session_factory) -> None:
    async with session_factory() as session:
        await append_agent_activity(
            session,
            agent_kind=AgentKind.ORCHESTRATOR,
            activity_state=AgentActivityState.COMPLETED,
            title="Order received",
            activity_key="order_received",
        )
        await append_agent_activity(
            session,
            agent_kind=AgentKind.INGESTION,
            activity_state=AgentActivityState.RUNNING,
            title="Extracting data",
            activity_key="extraction_started",
        )
        await session.commit()

    async with session_factory() as session:
        statuses = await get_agent_statuses(session)

        assert len(statuses) == 5
        orchestrator = next(s for s in statuses if s.agent_kind == AgentKind.ORCHESTRATOR)
        assert orchestrator.state == AgentActivityState.COMPLETED
        assert orchestrator.headline == "Order received"
        assert orchestrator.last_activity_at is not None


@pytest.mark.asyncio
async def test_get_agent_statuses_returns_empty_state(session_factory) -> None:
    async with session_factory() as session:
        statuses = await get_agent_statuses(session)

        assert len(statuses) == 5
        for status in statuses:
            assert status.last_activity_at is None
            assert status.active_item_count == 0


@pytest.mark.asyncio
async def test_get_orchestrator_timeline_returns_recent_activities(session_factory) -> None:
    async with session_factory() as session:
        await append_agent_activity(
            session,
            agent_kind=AgentKind.ORCHESTRATOR,
            activity_state=AgentActivityState.COMPLETED,
            title="Order received",
            activity_key="order_received",
        )
        await append_agent_activity(
            session,
            agent_kind=AgentKind.INGESTION,
            activity_state=AgentActivityState.COMPLETED,
            title="Extraction completed",
            activity_key="extraction_completed",
        )
        await session.commit()

    async with session_factory() as session:
        timeline = await get_orchestrator_timeline(session, limit=10)

        assert len(timeline) == 2
        titles = {item.title for item in timeline}
        assert titles == {"Order received", "Extraction completed"}
@pytest.mark.asyncio
async def test_timeline_includes_multi_agent_activities(session_factory) -> None:
    """Timeline returns activities from all agent kinds in correct order."""
    async with session_factory() as session:
        await append_agent_activity(
            session,
            agent_kind=AgentKind.ORCHESTRATOR,
            activity_state=AgentActivityState.COMPLETED,
            title="Order created",
            activity_key="order_created",
        )
        await append_agent_activity(
            session,
            agent_kind=AgentKind.INGESTION,
            activity_state=AgentActivityState.COMPLETED,
            title="Extraction finished",
            activity_key="extraction_finished",
        )
        await append_agent_activity(
            session,
            agent_kind=AgentKind.CARRIER_SEARCH,
            activity_state=AgentActivityState.COMPLETED,
            title="Search completed",
            activity_key="search_completed",
        )
        await session.commit()

    async with session_factory() as session:
        timeline = await get_orchestrator_timeline(session, limit=10)

        assert len(timeline) == 3
        agents = {item.agent for item in timeline}
        assert AgentKind.ORCHESTRATOR in agents
        assert AgentKind.INGESTION in agents
        assert AgentKind.CARRIER_SEARCH in agents


@pytest.mark.asyncio
async def test_ingestion_agent_kind_activity(session_factory) -> None:
    """append_agent_activity with INGESTION kind persists correctly."""
    async with session_factory() as session:
        await append_agent_activity(
            session,
            agent_kind=AgentKind.INGESTION,
            activity_state=AgentActivityState.COMPLETED,
            title="Extraction completed",
            activity_key="extraction_completed",
        )
        await session.commit()

    async with session_factory() as session:
        statuses = await get_agent_statuses(session)
        ingestion = next(s for s in statuses if s.agent_kind == AgentKind.INGESTION)
        assert ingestion.headline == "Extraction completed"
        assert ingestion.state == AgentActivityState.COMPLETED
        assert ingestion.last_activity_at is not None


@pytest.mark.asyncio
async def test_carrier_search_agent_kind_activity(session_factory) -> None:
    """append_agent_activity with CARRIER_SEARCH kind persists correctly."""
    async with session_factory() as session:
        await append_agent_activity(
            session,
            agent_kind=AgentKind.CARRIER_SEARCH,
            activity_state=AgentActivityState.RUNNING,
            title="Carrier search in progress",
            activity_key="carrier_search_dispatched",
        )
        await session.commit()

    async with session_factory() as session:
        statuses = await get_agent_statuses(session)
        cs = next(s for s in statuses if s.agent_kind == AgentKind.CARRIER_SEARCH)
        assert cs.headline == "Carrier search in progress"
        assert cs.state == AgentActivityState.RUNNING


@pytest.mark.asyncio
async def test_smart_comms_agent_kind_activity(session_factory) -> None:
    """append_agent_activity with SMART_COMMS kind persists correctly."""
    async with session_factory() as session:
        await append_agent_activity(
            session,
            agent_kind=AgentKind.SMART_COMMS,
            activity_state=AgentActivityState.COMPLETED,
            title="Assistant reply completed",
            activity_key="assistant_reply_completed",
        )
        await session.commit()

    async with session_factory() as session:
        statuses = await get_agent_statuses(session)
        sc = next(s for s in statuses if s.agent_kind == AgentKind.SMART_COMMS)
        assert sc.headline == "Assistant reply completed"
        assert sc.state == AgentActivityState.COMPLETED
