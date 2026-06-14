from httpx import AsyncClient
import pytest


async def _create_order(
    client: AsyncClient,
    *,
    distance_km: str | None = "1000.00",
) -> str:
    response = await client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_confirmed",
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "cargo_description": "Ceramic tiles",
            "weight_kg": "7800.00",
            "customer_price": "1400.00",
            "distance_km": distance_km,
            "truck_type_id": 1,
            "currency": "EUR",
            "missing_fields": {},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_post_carrier_search_creates_snapshot_and_transitions_order(
    auth_client: AsyncClient,
) -> None:
    order_id = await _create_order(auth_client)

    response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    assert response.status_code == 201
    body = response.json()
    assert body["load_order"]["id"] == order_id
    assert body["load_order"]["status"] == "searching_carrier"
    assert 3 <= len(body["candidates"]) <= 8

    detail_response = await auth_client.get(f"/api/v1/orders/{order_id}")

    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "searching_carrier"


@pytest.mark.asyncio
async def test_post_carrier_search_reuses_existing_snapshot_and_returns_200(
    auth_client: AsyncClient,
) -> None:
    order_id = await _create_order(auth_client)

    first_response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")
    second_response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    assert first_response.status_code == 201
    assert second_response.status_code == 200
    assert [item["trip_id"] for item in first_response.json()["candidates"]] == [
        item["trip_id"] for item in second_response.json()["candidates"]
    ]


@pytest.mark.asyncio
async def test_get_carrier_candidates_returns_existing_snapshot(
    auth_client: AsyncClient,
) -> None:
    order_id = await _create_order(auth_client)
    create_response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    response = await auth_client.get(f"/api/v1/orders/{order_id}/carrier-candidates")

    assert create_response.status_code == 201
    assert response.status_code == 200
    assert response.json() == create_response.json()


@pytest.mark.asyncio
async def test_get_carrier_candidates_returns_404_before_snapshot_exists(
    auth_client: AsyncClient,
) -> None:
    order_id = await _create_order(auth_client)

    response = await auth_client.get(f"/api/v1/orders/{order_id}/carrier-candidates")

    assert response.status_code == 404
    assert response.json()["detail"] == "Load order has no carrier-search snapshot"


@pytest.mark.asyncio
async def test_post_carrier_search_returns_422_when_distance_is_missing(
    auth_client: AsyncClient,
) -> None:
    order_id = await _create_order(auth_client, distance_km=None)

    response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    assert response.status_code == 422
    assert response.json()["detail"] == "Carrier search requires distance_km"


@pytest.mark.asyncio
async def test_post_carrier_search_rejects_viability_pending_order(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "cargo_description": "Ceramic tiles",
            "weight_kg": "7800.00",
            "customer_price": "1400.00",
            "distance_km": "1000.00",
            "truck_type_id": 1,
            "currency": "EUR",
            "missing_fields": {},
        },
    )
    assert response.status_code == 201
    order_id = response.json()["id"]

    search_response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    assert search_response.status_code == 409
    assert (
        search_response.json()["detail"]
        == "Carrier search not allowed for status: viability_pending"
    )


@pytest.mark.asyncio
async def test_post_carrier_search_openapi_documents_200_and_201(
    client: AsyncClient,
) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    responses = response.json()["paths"]["/api/v1/orders/{order_id}/carrier-search"]["post"][
        "responses"
    ]
    assert "200" in responses
    assert "201" in responses


# --- Protected browser contract tests ---

@pytest.mark.asyncio
async def test_post_carrier_search_with_auth_works_on_protected_router(
    auth_client: AsyncClient,
) -> None:
    order_id = await _create_order(auth_client)

    response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    assert response.status_code == 201
    body = response.json()
    assert body["load_order"]["id"] == order_id
    assert body["load_order"]["status"] == "searching_carrier"


@pytest.mark.asyncio
async def test_get_carrier_candidates_with_auth_works_on_protected_router(
    auth_client: AsyncClient,
) -> None:
    order_id = await _create_order(auth_client)
    await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    response = await auth_client.get(f"/api/v1/orders/{order_id}/carrier-candidates")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_post_carrier_search_without_auth_is_rejected(
    client: AsyncClient,
    auth_client: AsyncClient,
) -> None:
    order_id = await _create_order(auth_client)

    response = await client.post(f"/api/v1/orders/{order_id}/carrier-search")

    assert response.status_code == 401


# ─── Auto carrier search log activity unit test ────────────────────────────

@pytest.mark.asyncio
async def test_auto_carrier_search_log_activity() -> None:
    from app.backend.models.user import User
    from app.backend.models.load_order import LoadOrder
    from app.backend.core.domain_enums import AgentKind, AgentActivityState, LoadOrderStatus
    from app.backend.services.load_order_orchestrator import log_auto_carrier_search_triggered
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from uuid import uuid4

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import app.backend.models  # noqa
    from app.backend.db.base import Base

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            user = User(id=uuid4(), email="t@t.com", operator_name="T", auth_id="t")
            order = LoadOrder(
                user=user, status=LoadOrderStatus.VIABILITY_CONFIRMED, currency="EUR"
            )
            session.add_all([user, order])
            await session.flush()

            activity = await log_auto_carrier_search_triggered(session, order)
            await session.commit()

            assert activity.agent_kind == AgentKind.ORCHESTRATOR
            assert activity.activity_key == "auto_carrier_search_triggered"
            assert activity.activity_state == AgentActivityState.COMPLETED
            assert "auto" in activity.title.lower()
    finally:
        await engine.dispose()
