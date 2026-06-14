"""Unit tests for Smart Comms conversation and message persistence."""

from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backend.core.domain_enums import SmartCommsContextType, SmartCommsMessageRole
from app.backend.db.base import Base
from app.backend.models.user import User
from app.backend.services.chroma_runtime import _reset_client
from app.backend.services.smart_comms_service import (
    resolve_conversation,
    persist_user_message,
    persist_assistant_message,
    get_conversation_messages,
    get_conversation_or_404_for_user,
)


@pytest_asyncio.fixture
async def engine():
    return create_async_engine("sqlite+aiosqlite:///:memory:", future=True)


@pytest_asyncio.fixture
async def session_factory(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _isolate_chroma(tmp_path: Path) -> None:
    _reset_client()
    yield
    _reset_client()


@pytest.mark.asyncio
async def test_resolve_conversation_creates_new(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        session.add(user)
        await session.flush()

        conversation = await resolve_conversation(
            session,
            user_id=user.id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/dashboard",
        )
        await session.commit()

        assert conversation.id is not None
        assert conversation.user_id == user.id
        assert conversation.context_type == SmartCommsContextType.DASHBOARD
        assert conversation.route_path == "/dashboard"


@pytest.mark.asyncio
async def test_resolve_conversation_reuses_existing(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        session.add(user)
        await session.flush()

        conv1 = await resolve_conversation(
            session,
            user_id=user.id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/dashboard",
        )
        await session.commit()

    async with session_factory() as session:
        conv2 = await resolve_conversation(
            session,
            user_id=user.id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/dashboard",
        )
        await session.commit()

        assert conv1.id == conv2.id


@pytest.mark.asyncio
async def test_persist_user_message(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        session.add(user)
        await session.flush()

        conversation = await resolve_conversation(
            session,
            user_id=user.id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/dashboard",
        )
        await session.flush()

        message = await persist_user_message(session, conversation.id, "What orders are pending?")
        await session.commit()

        assert message.id is not None
        assert message.conversation_id == conversation.id
        assert message.role == SmartCommsMessageRole.USER
        assert message.content == "What orders are pending?"


@pytest.mark.asyncio
async def test_persist_assistant_message(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        session.add(user)
        await session.flush()

        conversation = await resolve_conversation(
            session,
            user_id=user.id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/dashboard",
        )
        await session.flush()

        await persist_user_message(session, conversation.id, "Hello")
        message = await persist_assistant_message(
            session, conversation.id, "Hello! How can I help?"
        )
        await session.commit()

        assert message.role == SmartCommsMessageRole.ASSISTANT
        assert message.content == "Hello! How can I help?"


@pytest.mark.asyncio
async def test_get_conversation_messages(session_factory) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="test@example.com",
            operator_name="Test",
            auth_id="auth_test",
        )
        session.add(user)
        await session.flush()

        conversation = await resolve_conversation(
            session,
            user_id=user.id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/dashboard",
        )
        await session.flush()

        await persist_user_message(session, conversation.id, "Hello")
        await persist_assistant_message(session, conversation.id, "Hi there!")
        await session.commit()

    async with session_factory() as session:
        messages = await get_conversation_messages(session, conversation.id)

        assert len(messages) == 2
        assert messages[0].role == SmartCommsMessageRole.USER
        assert messages[1].role == SmartCommsMessageRole.ASSISTANT


@pytest.mark.asyncio
async def test_get_conversation_or_404_returns_own_conversation(session_factory) -> None:
    """The helper returns the conversation when it belongs to the requesting user."""
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="owner@example.com",
            operator_name="Owner",
            auth_id="auth_owner",
        )
        session.add(user)
        await session.flush()

        conversation = await resolve_conversation(
            session,
            user_id=user.id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/dashboard",
        )
        await session.commit()

    async with session_factory() as session:
        found = await get_conversation_or_404_for_user(session, conversation.id, user.id)
        assert found is not None
        assert found.id == conversation.id


@pytest.mark.asyncio
async def test_get_conversation_or_404_returns_none_for_other_user(session_factory) -> None:
    """The helper returns None when the conversation does not belong to the requesting user."""
    async with session_factory() as session:
        owner = User(
            id=uuid4(),
            email="owner@example.com",
            operator_name="Owner",
            auth_id="auth_owner",
        )
        intruder = User(
            id=uuid4(),
            email="intruder@example.com",
            operator_name="Intruder",
            auth_id="auth_intruder",
        )
        session.add_all([owner, intruder])
        await session.flush()

        conversation = await resolve_conversation(
            session,
            user_id=owner.id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/dashboard",
        )
        await session.commit()

    async with session_factory() as session:
        result = await get_conversation_or_404_for_user(session, conversation.id, intruder.id)
        assert result is None


@pytest.mark.asyncio
async def test_get_conversation_or_404_returns_none_for_missing_id(session_factory) -> None:
    """The helper returns None when the conversation UUID does not exist."""
    async with session_factory() as session:
        result = await get_conversation_or_404_for_user(
            session,
            uuid4(),
            uuid4(),
        )
        assert result is None


@pytest.mark.asyncio
async def test_json_payload_roundtrips_multiline_markdown(session_factory) -> None:
    """Confirm that JSON serialization preserves multiline markdown chunks."""
    import json

    multiline = "## Summary\n- point one\n- **point two**\n\nDone."

    payload = json.dumps({"chunk": multiline})
    restored = json.loads(payload)
    assert restored["chunk"] == multiline
    assert "\n" in restored["chunk"]


# ─── Smart Comms retrieval tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieval_returns_empty_when_no_memory(session_factory) -> None:
    from app.backend.services.rag_memory import retrieve_smart_comms_context

    results = retrieve_smart_comms_context("test query", top_k=3)
    assert results == []


@pytest.mark.asyncio
async def test_retrieval_finds_indexed_memory(session_factory) -> None:
    from app.backend.services.chroma_runtime import _reset_client
    from app.backend.services.rag_memory import (
        index_smart_comms_memory,
        retrieve_smart_comms_context,
    )

    _reset_client()
    try:
        index_smart_comms_memory(
            order_id="order-99",
            customer_name="TestCo",
            route_label="Bilbao -> Frankfurt",
            operator_question="What carrier?",
            assistant_response="Use CarrierA.",
        )

        results = retrieve_smart_comms_context("Bilbao Frankfurt carrier", top_k=3)
        assert len(results) >= 1
        assert "TestCo" in results[0]["document"]
    finally:
        _reset_client()


@pytest.mark.asyncio
async def test_retrieval_does_not_break_with_empty_memory(session_factory) -> None:
    from app.backend.services.rag_memory import retrieve_smart_comms_context

    results = retrieve_smart_comms_context("anything", top_k=3)
    assert isinstance(results, list)
