"""API tests for Smart Comms endpoints."""

import json
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select
from unittest.mock import AsyncMock, MagicMock, patch

from app.backend.core.domain_enums import LoadOrderStatus, SmartCommsContextType
from app.backend.api.dependencies.auth import get_current_user
from app.backend.core.domain_enums import AgentActivityState, AgentKind
from app.backend.db.base import Base
from app.backend.db.session import get_async_session, AsyncSessionDep
from app.backend.main import create_app
from app.backend.models.agent_activity import AgentActivity
from app.backend.models.load_order import LoadOrder
from app.backend.models.user import User
from app.backend.services.smart_comms_service import resolve_conversation


@pytest.mark.asyncio
async def test_resolve_conversation_creates_new(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={
            "context_type": "dashboard",
            "route_path": "/dashboard",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["context_type"] == "dashboard"
    assert data["route_path"] == "/dashboard"
    assert "id" in data


@pytest.mark.asyncio
async def test_resolve_conversation_reuses_existing(auth_client: AsyncClient) -> None:
    response1 = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={
            "context_type": "dashboard",
            "route_path": "/dashboard",
        },
    )
    response2 = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={
            "context_type": "dashboard",
            "route_path": "/dashboard",
        },
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["id"] == response2.json()["id"]


@pytest.mark.asyncio
async def test_smart_comms_endpoints_require_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={
            "context_type": "dashboard",
            "route_path": "/dashboard",
        },
    )
    assert response.status_code == 401 or response.status_code == 403


@pytest.mark.asyncio
async def test_stream_returns_404_for_missing_conversation(auth_client: AsyncClient) -> None:
    """Streaming to a non-existent conversation returns 404."""
    response = await auth_client.post(
        "/api/v1/smart-comms/conversations/00000000-0000-0000-0000-000000000000/messages/stream",
        json={"content": "Hello"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stream_returns_404_for_non_owned_conversation(tmp_path) -> None:
    """A conversation owned by one user cannot be streamed by another authenticated user."""
    from uuid import uuid4

    test_db_path = tmp_path / "test_ownership.db"
    test_db_url = f"sqlite+aiosqlite:///{test_db_path.as_posix()}"

    engine = create_async_engine(test_db_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    owner_id = uuid4()
    intruder_id = uuid4()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all([
            User(id=owner_id, email="owner@ex.com", operator_name="Owner", auth_id="auth_o"),
            User(id=intruder_id, email="intruder@ex.com", operator_name="Bad", auth_id="auth_b"),
        ])
        await session.commit()

    from app.backend.services.smart_comms_service import resolve_conversation
    from app.backend.core.domain_enums import SmartCommsContextType

    async with session_factory() as session:
        conv = await resolve_conversation(
            session,
            user_id=owner_id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/dashboard",
        )
        await session.commit()
        conv_id = str(conv.id)

    app = create_app()

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_intruder_user(session: AsyncSessionDep):
        return await session.get(User, intruder_id)

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_intruder_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                f"/api/v1/smart-comms/conversations/{conv_id}/messages/stream",
                json={"content": "Hello"},
            )
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_messages_returns_chronological_history(auth_client: AsyncClient) -> None:
    """GET messages returns persisted messages in chronological order."""
    resolve_resp = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={"context_type": "dashboard", "route_path": "/dashboard"},
    )
    conv_id = resolve_resp.json()["id"]

    await auth_client.post(
        f"/api/v1/smart-comms/conversations/{conv_id}/messages/stream",
        json={"content": "ping"},
    )

    resp = await auth_client.get(
        f"/api/v1/smart-comms/conversations/{conv_id}/messages",
    )
    assert resp.status_code == 200
    messages = resp.json()
    assert isinstance(messages, list)
    assert len(messages) >= 1
    user_messages = [m for m in messages if m["role"] == "user"]
    assert len(user_messages) >= 1
    assert user_messages[0]["content"] == "ping"


@pytest.mark.asyncio
async def test_get_messages_returns_404_for_non_owned_conversation(tmp_path) -> None:
    """Message history of a conversation owned by another user is not exposed."""
    from uuid import uuid4

    test_db_path = tmp_path / "test_history_owner.db"
    test_db_url = f"sqlite+aiosqlite:///{test_db_path.as_posix()}"

    engine = create_async_engine(test_db_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    owner_id = uuid4()
    intruder_id = uuid4()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all([
            User(id=owner_id, email="a@b.com", operator_name="O", auth_id="a1"),
            User(id=intruder_id, email="c@d.com", operator_name="I", auth_id="a2"),
        ])
        await session.commit()

    from app.backend.services.smart_comms_service import resolve_conversation
    from app.backend.core.domain_enums import SmartCommsContextType

    async with session_factory() as session:
        conv = await resolve_conversation(
            session,
            user_id=owner_id,
            context_type=SmartCommsContextType.DASHBOARD,
            route_path="/d",
        )
        await session.commit()
        conv_id = str(conv.id)

    app = create_app()

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_intruder_user(session: AsyncSessionDep):
        return await session.get(User, intruder_id)

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_intruder_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                f"/api/v1/smart-comms/conversations/{conv_id}/messages",
            )
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_smart_comms_runtime_uses_reasoning_model_name() -> None:
    from app.backend.services.smart_comms_runtime import stream_chat_response
    from app.backend.core.settings import Settings

    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///./tests.db",
        REASONING_MODEL_PROVIDER="openrouter",
        REASONING_MODEL_NAME="deepseek/deepseek-v4-flash",
        REASONING_MODEL_API_KEY="sk-test",
    )

    with patch("app.backend.services.smart_comms_runtime.get_settings", return_value=settings):
        with patch("app.backend.services.smart_comms_runtime.stream_completion") as mock_stream:
            async def _empty_stream(*args, **kwargs):
                yield ""
                return
            mock_stream.side_effect = _empty_stream

            chunks = []
            async for chunk in stream_chat_response([{"role": "user", "content": "Hi"}]):
                chunks.append(chunk)

            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs["profile"] == "reasoning"
            assert call_kwargs["settings"] == settings


@pytest.mark.asyncio
async def test_smart_comms_runtime_not_configured_message_refers_reasoning_model() -> None:
    from app.backend.services.smart_comms_runtime import stream_chat_response
    from app.backend.core.settings import Settings

    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///./tests.db",
        REASONING_MODEL_NAME="",
    )

    with patch("app.backend.services.smart_comms_runtime.get_settings", return_value=settings):
        chunks = []
        async for chunk in stream_chat_response([{"role": "user", "content": "Hi"}]):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "REASONING_MODEL_NAME" in chunks[0].replace(" ", "")


@pytest.mark.asyncio
async def test_smart_comms_stream_persists_response(auth_client: AsyncClient) -> None:
    """Streaming to a conversation persists a user message and yields an assistant response."""
    resolve_resp = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={"context_type": "dashboard", "route_path": "/dashboard"},
    )
    conv_id = resolve_resp.json()["id"]

    response = await auth_client.post(
        f"/api/v1/smart-comms/conversations/{conv_id}/messages/stream",
        json={"content": "Hello"},
    )
    assert response.status_code == 200
    response_text = response.text
    assert "event: error" not in response_text, f"Error in stream: {response_text[:500]}"

    messages_resp = await auth_client.get(
        f"/api/v1/smart-comms/conversations/{conv_id}/messages",
    )
    assert messages_resp.status_code == 200
    messages = messages_resp.json()
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1, f"Messages: {messages}"


@pytest.mark.asyncio
async def test_smart_comms_load_order_stream_works_when_retrieval_disabled(tmp_path) -> None:
    test_db_path = tmp_path / "test_smart_comms_load_order.db"
    test_db_url = f"sqlite+aiosqlite:///{test_db_path.as_posix()}"

    engine = create_async_engine(test_db_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user = User(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        email="operator@example.com",
        operator_name="Operator Demo",
        auth_id="auth_demo",
    )

    async with session_factory() as session:
        session.add(user)
        await session.flush()
        order = LoadOrder(
            user_id=user.id,
            status=LoadOrderStatus.VIABILITY_PENDING,
            customer_name="Acme Logistics",
            origin_text="Madrid, ES",
            destination_text="Paris, FR",
            cargo_description="Ceramic tiles",
            currency="EUR",
        )
        session.add(order)
        await session.flush()
        await resolve_conversation(
            session,
            user_id=user.id,
            context_type=SmartCommsContextType.LOAD_ORDER,
            context_id=order.id,
            route_path=f"/orders/{order.id}",
        )
        await session.commit()

    app = create_app()

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_get_current_user(session: AsyncSessionDep) -> User:
        return await session.get(User, user.id)

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            async with session_factory() as session:
                conv = await resolve_conversation(
                    session,
                    user_id=user.id,
                    context_type=SmartCommsContextType.LOAD_ORDER,
                    context_id=order.id,
                    route_path=f"/orders/{order.id}",
                )
                await session.commit()
                conv_id = conv.id

            response = await client.post(
                f"/api/v1/smart-comms/conversations/{conv_id}/messages/stream",
                json={"content": "Summarize this order"},
            )
            assert response.status_code == 200
            assert "event: error" not in response.text
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_stream_prompt_includes_real_summary_data(auth_client: AsyncClient) -> None:
    await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "customer_name": "Needs Review",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "cargo_description": "Tiles",
            "currency": "EUR",
        },
    )
    resolve_resp = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={"context_type": "dashboard", "route_path": "/dashboard"},
    )
    conv_id = resolve_resp.json()["id"]

    captured_messages: list[dict[str, str]] = []

    async def fake_stream_chat_response(messages):
        captured_messages.extend(messages)
        yield "ok"

    with patch("app.backend.api.endpoints.smart_comms.stream_chat_response", side_effect=fake_stream_chat_response):
        response = await auth_client.post(
            f"/api/v1/smart-comms/conversations/{conv_id}/messages/stream",
            json={"content": "What needs attention?"},
        )

    assert response.status_code == 200
    system_prompt = captured_messages[0]["content"]
    assert "Active orders:" in system_prompt
    assert "Needs Review" in system_prompt
    assert "Agent status cards:" in system_prompt


@pytest.mark.asyncio
async def test_orders_list_stream_prompt_includes_loaded_orders_and_counts(auth_client: AsyncClient) -> None:
    await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "cargo_description": "Tiles",
            "currency": "EUR",
        },
    )
    await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "formalized",
            "customer_name": "Maria",
            "origin_text": "Valencia, ES",
            "destination_text": "Berlin, DE",
            "cargo_description": "Produce",
            "currency": "EUR",
        },
    )
    resolve_resp = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={"context_type": "orders_list", "route_path": "/orders"},
    )
    conv_id = resolve_resp.json()["id"]

    captured_messages: list[dict[str, str]] = []

    async def fake_stream_chat_response(messages):
        captured_messages.extend(messages)
        yield "ok"

    with patch("app.backend.api.endpoints.smart_comms.stream_chat_response", side_effect=fake_stream_chat_response):
        response = await auth_client.post(
            f"/api/v1/smart-comms/conversations/{conv_id}/messages/stream",
            json={"content": "How many orders are in each status?"},
        )

    assert response.status_code == 200
    system_prompt = captured_messages[0]["content"]
    assert "Status counts in loaded items:" in system_prompt
    assert "viability_pending: 1" in system_prompt
    assert "formalized: 1" in system_prompt
    assert "Acme Logistics" in system_prompt
    assert "Maria" in system_prompt


@pytest.mark.asyncio
async def test_settings_stream_prompt_includes_runtime_values(auth_client: AsyncClient) -> None:
    await auth_client.put(
        "/api/v1/settings/runtime",
        json={
            "enable_auto_carrier_search": True,
            "enable_smart_comms_retrieval": True,
        },
    )
    resolve_resp = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={"context_type": "settings", "route_path": "/settings"},
    )
    conv_id = resolve_resp.json()["id"]

    captured_messages: list[dict[str, str]] = []

    async def fake_stream_chat_response(messages):
        captured_messages.extend(messages)
        yield "ok"

    with patch("app.backend.api.endpoints.smart_comms.stream_chat_response", side_effect=fake_stream_chat_response):
        response = await auth_client.post(
            f"/api/v1/smart-comms/conversations/{conv_id}/messages/stream",
            json={"content": "Explain the current runtime settings"},
        )

    assert response.status_code == 200
    system_prompt = captured_messages[0]["content"]
    assert "Runtime settings:" in system_prompt
    assert "Auto carrier search: True" in system_prompt
    assert "Smart Comms retrieval: True" in system_prompt


@pytest.mark.asyncio
async def test_intake_review_stream_prompt_includes_missing_field_context(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Cargo: Ceramic tiles",
                ]
            ),
        },
    )
    assert response.status_code == 201
    order_id = response.json()["load_order"]["id"]

    resolve_resp = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={"context_type": "intake_review", "context_id": order_id, "route_path": f"/orders/{order_id}/intake"},
    )
    conv_id = resolve_resp.json()["id"]

    captured_messages: list[dict[str, str]] = []

    async def fake_stream_chat_response(messages):
        captured_messages.extend(messages)
        yield "ok"

    with patch("app.backend.api.endpoints.smart_comms.stream_chat_response", side_effect=fake_stream_chat_response):
        stream_response = await auth_client.post(
            f"/api/v1/smart-comms/conversations/{conv_id}/messages/stream",
            json={"content": "What is missing from this intake?"},
        )

    assert stream_response.status_code == 200
    system_prompt = captured_messages[0]["content"]
    assert "Missing fields:" in system_prompt
    assert "destination_text" in system_prompt
    assert "origin_load_date" in system_prompt


@pytest.mark.asyncio
async def test_smart_comms_stream_records_running_and_completed_activity(tmp_path) -> None:
    test_db_path = tmp_path / "test_smart_comms_activity.db"
    test_db_url = f"sqlite+aiosqlite:///{test_db_path.as_posix()}"

    engine = create_async_engine(test_db_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user = User(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        email="operator@example.com",
        operator_name="Operator Demo",
        auth_id="auth_demo",
    )

    async with session_factory() as session:
        session.add(user)
        await session.commit()

    app = create_app()

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_get_current_user(session: AsyncSessionDep) -> User:
        return await session.get(User, user.id)

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            resolve_resp = await client.post(
                "/api/v1/smart-comms/conversations/resolve",
                json={"context_type": "dashboard", "route_path": "/dashboard"},
            )
            conv_id = resolve_resp.json()["id"]

            response = await client.post(
                f"/api/v1/smart-comms/conversations/{conv_id}/messages/stream",
                json={"content": "Hello"},
            )
            assert response.status_code == 200

        async with session_factory() as session:
            result = await session.execute(
                select(AgentActivity)
                .where(AgentActivity.agent_kind == AgentKind.SMART_COMMS)
                .order_by(AgentActivity.created_at.asc())
            )
            activities = list(result.scalars().all())

        assert [activity.activity_key for activity in activities[-2:]] == [
            "assistant_reply_started",
            "assistant_reply_completed",
        ]
        assert activities[-2].activity_state == AgentActivityState.RUNNING
        assert activities[-1].activity_state == AgentActivityState.COMPLETED
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
