"""API tests for execution monitoring endpoints."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backend.api.dependencies.auth import get_current_user
from app.backend.db.base import Base
from app.backend.db.session import AsyncSessionDep, get_async_session
from app.backend.main import create_app
from app.backend.models.load_order import LoadOrder
from app.backend.models.user import User
from app.backend.tests.conftest import SEEDED_USER_ID


@pytest.mark.asyncio
async def test_execution_monitoring_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/monitoring/orders/00000000-0000-0000-0000-000000000000/execution")
    assert response.status_code == 401 or response.status_code == 403


@pytest.mark.asyncio
async def test_execution_monitoring_returns_persisted_snapshot_without_refreshing(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "formalized",
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "cargo_description": "Ceramic tiles",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    response = await auth_client.get(f"/api/v1/monitoring/orders/{order_id}/execution")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["load_order_id"] == order_id
    assert body["snapshot"]["status"] == "planned"
    assert body["snapshot"]["current_checkpoint"] == "Madrid, ES"
    assert body["snapshot"]["route_points"][0]["label"] == "Madrid, ES"
    assert body["snapshot"]["route_points"][-1]["label"] == "Paris, FR"
    assert len(body["snapshot"]["route_points"]) == 4
    assert len(body["snapshot"]["route_path"]) >= 2
    assert body["snapshot"]["current_position"]["label"] == "Madrid, ES"
    assert body["shipment"]["route_label"] == "Madrid, ES -> Paris, FR"
    assert body["shipment"]["cargo_description"] == "Ceramic tiles"
    assert body["agent_update"]["source"] == "deterministic"
    assert body["alerts"] == []


@pytest.mark.asyncio
async def test_execution_monitoring_returns_404_when_snapshot_missing(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/api/v1/monitoring/orders/00000000-0000-0000-0000-000000000000/execution")

    assert response.status_code == 404
    assert response.json()["detail"] == "Execution monitoring snapshot not initialized"


@pytest.mark.asyncio
async def test_execution_monitoring_refresh_advances_persisted_route_state(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "formalized",
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "distance_km": "1270.00",
            "cargo_description": "Ceramic tiles",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    refresh_response = await auth_client.post(f"/api/v1/monitoring/orders/{order_id}/refresh")

    assert refresh_response.status_code == 200
    body = refresh_response.json()
    assert body["snapshot"]["progress_percent"] > 0
    assert len(body["snapshot"]["events"]) >= 2
    assert body["snapshot"]["current_position"]["label"] != "Paris, FR"
    assert body["shipment"]["last_update_source"] == "operator_refresh"

    read_response = await auth_client.get(f"/api/v1/monitoring/orders/{order_id}/execution")
    read_body = read_response.json()
    assert read_body["snapshot"]["progress_percent"] == body["snapshot"]["progress_percent"]
    assert len(read_body["snapshot"]["events"]) == len(body["snapshot"]["events"])


@pytest.mark.asyncio
async def test_execution_monitoring_refresh_can_be_repeated_without_server_error(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "formalized",
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "distance_km": "1270.00",
            "cargo_description": "Ceramic tiles",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    statuses: list[int] = []
    for _ in range(4):
        refresh_response = await auth_client.post(f"/api/v1/monitoring/orders/{order_id}/refresh")
        statuses.append(refresh_response.status_code)

    assert statuses == [200, 200, 200, 200]


@pytest.mark.asyncio
async def test_execution_monitoring_initializes_snapshot_for_existing_order_without_one(
    tmp_path: Path,
) -> None:
    test_database_path = tmp_path / "legacy-monitoring.db"
    test_database_url = f"sqlite+aiosqlite:///{test_database_path.as_posix()}"

    engine = create_async_engine(test_database_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = User(
            id=SEEDED_USER_ID,
            email="operator@example.com",
            operator_name="Operator Demo",
            auth_id="auth_demo",
        )
        order = LoadOrder(
            user=user,
            status="formalized",
            customer_name="Legacy Logistics",
            origin_text="Valencia, ES",
            destination_text="Lyon, FR",
            cargo_description="Paper reels",
            currency="EUR",
        )
        session.add_all([user, order])
        await session.commit()
        await session.refresh(order)
        order_id = order.id

    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    async def override_get_current_user(session: AsyncSessionDep) -> User:
        user = await session.get(User, SEEDED_USER_ID)
        return user

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(f"/api/v1/monitoring/orders/{order_id}/execution")

    app.dependency_overrides.clear()
    await engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["load_order_id"] == str(order_id)
    assert body["snapshot"]["current_checkpoint"] == "Valencia, ES"
