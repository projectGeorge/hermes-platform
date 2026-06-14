import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backend.models.user import User


SEEDED_USER_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_create_and_get_order(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "cargo_description": "Palets de producto seco",
            "weight_kg": "1200.00",
            "customer_price": "950.00",
            "currency": "EUR",
        },
    )
    assert create_response.status_code == 201

    order_id = create_response.json()["id"]
    detail_response = await auth_client.get(f"/api/v1/orders/{order_id}")

    assert detail_response.status_code == 200
    assert detail_response.json()["user_id"] == SEEDED_USER_ID


@pytest.mark.asyncio
async def test_create_order_derives_viability_confirmed_when_manual_payload_is_complete(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "origin_load_date": "2026-05-04T09:30:00",
            "cargo_description": "Ceramic tiles",
            "weight_kg": "7800.00",
            "customer_price": "1400.00",
            "distance_km": "1270.00",
            "truck_type_id": 1,
            "currency": "EUR",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "viability_confirmed"
    assert body["missing_fields"] is None


@pytest.mark.asyncio
async def test_list_orders_page_returns_paginated_filtered_results(
    auth_client: AsyncClient,
) -> None:
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
            "status": "cancelled",
            "customer_name": "Old Customer",
            "origin_text": "Porto, PT",
            "destination_text": "Lyon, FR",
            "cargo_description": "Archived load",
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
            "cargo_description": "Fresh produce",
            "currency": "EUR",
        },
    )

    response = await auth_client.get(
        "/api/v1/orders/page?limit=1&skip=0&active_only=true&search=maria"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["skip"] == 0
    assert body["limit"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["customer_name"] == "Maria"
    assert body["items"][0]["status"] == "formalized"


@pytest.mark.asyncio
async def test_orders_summary_returns_dashboard_counts_and_recent_items(
    auth_client: AsyncClient,
) -> None:
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
    await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "formalized",
            "customer_name": "Ready Shipment",
            "origin_text": "Valencia, ES",
            "destination_text": "Berlin, DE",
            "cargo_description": "Produce",
            "currency": "EUR",
        },
    )
    await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "cancelled",
            "customer_name": "Cancelled Job",
            "origin_text": "Porto, PT",
            "destination_text": "Lyon, FR",
            "cargo_description": "Archived load",
            "currency": "EUR",
        },
    )

    response = await auth_client.get("/api/v1/orders/summary?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body["active_order_count"] == 2
    assert body["needs_attention_count"] == 1
    assert [item["customer_name"] for item in body["attention_orders"]] == ["Needs Review"]
    assert {item["customer_name"] for item in body["recent_active_orders"]} == {
        "Needs Review",
        "Ready Shipment",
    }


@pytest.mark.asyncio
async def test_create_order_returns_english_validation_error_for_invalid_schedule(
    auth_client: AsyncClient,
) -> None:
    invalid_payload = {
        "status": "viability_pending",
        "cargo_description": "Palets de producto seco",
        "weight_kg": "1200.00",
        "customer_price": "950.00",
        "currency": "EUR",
        "origin_load_date": "2026-04-11T10:00:00",
        "destination_unload_date": "2026-04-10T10:00:00",
    }

    response = await auth_client.post("/api/v1/orders/", json=invalid_payload)

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "destination_unload_date cannot be earlier than origin_load_date"
    )


@pytest.mark.asyncio
async def test_cancel_order_changes_status(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "cargo_description": "Palets de producto seco",
            "weight_kg": "1200.00",
            "customer_price": "950.00",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    cancel_response = await auth_client.post(f"/api/v1/orders/{order_id}/cancel")

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_formalize_requires_valid_status(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "cargo_description": "Palets de producto seco",
            "weight_kg": "1200.00",
            "customer_price": "950.00",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    formalize_response = await auth_client.post(f"/api/v1/orders/{order_id}/formalize")

    assert formalize_response.status_code == 409
    assert (
        formalize_response.json()["detail"]
        == "Transition not allowed: viability_pending -> formalized"
    )


@pytest.mark.asyncio
async def test_update_order_returns_english_conflict_for_invalid_transition(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "cargo_description": "Palets de producto seco",
            "weight_kg": "1200.00",
            "customer_price": "950.00",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    update_response = await auth_client.put(
        f"/api/v1/orders/{order_id}",
        json={"status": "ready_for_formalization"},
    )

    assert update_response.status_code == 409
    assert (
        update_response.json()["detail"]
        == "Transition not allowed: viability_pending -> ready_for_formalization"
    )


@pytest.mark.asyncio
async def test_manual_orchestrator_refresh_logs_current_workflow_state(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "cargo_description": "Palets de producto seco",
            "weight_kg": "1200.00",
            "customer_price": "950.00",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    refresh_response = await auth_client.post(
        f"/api/v1/orders/{order_id}/orchestrator-refresh"
    )

    assert refresh_response.status_code == 200
    assert refresh_response.json()["activity_key"] == "orchestrator_manual_refresh"
    assert refresh_response.json()["load_order_id"] == order_id
    assert "workflow state" in (refresh_response.json()["detail"] or "")


@pytest.mark.asyncio
async def test_delegated_orchestrator_extracts_email_into_order_draft(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/orders/delegated-actions",
        json={
            "action": "extract_email_into_order_draft",
            "source_email_text": "Customer: Acme Logistics\nOrigin: Madrid, ES\nDestination: Paris, FR\nLoad Date: 2026-05-04 09:30\nCargo: Ceramic tiles",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delegated_to"] == "ingestion"
    assert body["activity"]["activity_key"] == "delegated_intake_extraction"
    assert body["activity"]["metadata"]["delegated_action"] == "extract_email_into_order_draft"
    assert body["ingestion_result"]["load_order"]["customer_name"] == "Acme Logistics"


@pytest.mark.asyncio
async def test_delegated_orchestrator_extracts_common_pasted_email_shape(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/orders/delegated-actions",
        json={
            "action": "extract_email_into_order_draft",
            "source_email_text": "Subject: Shipment request\nCustomer: Acme Logistics\nPickup: Madrid, ES\nDelivery: Paris, FR\nLoading date: 2026-05-04 09:30\nCommodity: Ceramic tiles\nWeight: 7800\nPrice: 1250.50 EUR",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ingestion_result"]["load_order"]["origin_text"] == "Madrid, ES"
    assert body["ingestion_result"]["load_order"]["destination_text"] == "Paris, FR"
    assert body["ingestion_result"]["load_order"]["cargo_description"] == "Ceramic tiles"


@pytest.mark.asyncio
async def test_delegated_orchestrator_extracts_email_with_real_postgres_schema(
) -> None:
    database_url = "postgresql+asyncpg://hermes_user:hermes_password@localhost:5432/hermes_db"
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT version_num FROM alembic_version"
            )
        )
        assert result.scalar_one() in {"20260530_01", "ab14c5059df5", "3cd0f4ac9318"}

        seeded_user = await session.get(User, SEEDED_USER_ID)
        if seeded_user is None:
            session.add(
                User(
                    id=SEEDED_USER_ID,
                    email="operator@example.com",
                    operator_name="Operator Demo",
                    auth_id="auth_demo",
                )
            )
            await session.commit()

    from app.backend.api.dependencies.auth import get_current_user
    from app.backend.db.session import get_async_session
    from app.backend.main import create_app

    app = create_app()

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_get_current_user():
        async with session_factory() as session:
            user = await session.get(User, SEEDED_USER_ID)
            assert user is not None
            return user

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/orders/delegated-actions",
            json={
                "action": "extract_email_into_order_draft",
                "source_email_text": "Subject: Shipment request\nCustomer: Acme Logistics\nPickup: Madrid, ES\nDelivery: Paris, FR\nLoading date: 2026-05-04 09:30\nCommodity: Ceramic tiles\nWeight: 7800\nPrice: 1250.50 EUR",
            },
        )

    app.dependency_overrides.clear()
    await engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["delegated_to"] == "ingestion"
    assert body["ingestion_result"]["load_order"]["origin_text"] == "Madrid, ES"
    assert body["ingestion_result"]["load_order"]["destination_text"] == "Paris, FR"


@pytest.mark.asyncio
async def test_delegated_orchestrator_opens_smart_comms_for_order(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "origin_load_date": "2026-06-15T09:00:00",
            "cargo_description": "Ceramic tiles",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    response = await auth_client.post(
        "/api/v1/orders/delegated-actions",
        json={
            "action": "draft_message",
            "load_order_id": order_id,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delegated_to"] == "smart_comms"
    assert body["activity"]["activity_key"] == "delegated_smart_comms_opened"
    assert body["smart_comms_conversation"]["context_type"] == "load_order"
    assert body["smart_comms_conversation"]["context_id"] == order_id


@pytest.mark.asyncio
async def test_formalize_requires_selected_trip_after_search(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_confirmed",
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
    order_id = create_response.json()["id"]
    search_response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    assert search_response.status_code == 201

    formalize_response = await auth_client.post(f"/api/v1/orders/{order_id}/formalize")

    assert formalize_response.status_code == 409
    assert (
        formalize_response.json()["detail"]
        == "Carrier selection required before ready_for_formalization"
    )


# --- Protected browser contract tests ---

@pytest.mark.asyncio
async def test_create_order_without_auth_is_rejected(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/orders/",
        json={
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "cargo_description": "Ceramic tiles",
            "currency": "EUR",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_order_with_auth_succeeds_without_explicit_user_id(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "origin_load_date": "2026-06-15T09:00:00",
            "cargo_description": "Ceramic tiles",
            "currency": "EUR",
        },
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == SEEDED_USER_ID
    assert response.json()["customer_name"] == "Acme Logistics"


@pytest.mark.asyncio
async def test_create_order_derives_viability_confirmed_when_manual_payload_is_complete(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "origin_load_date": "2026-05-04T09:30:00",
            "cargo_description": "Ceramic tiles",
            "weight_kg": "7800.00",
            "customer_price": "1400.00",
            "distance_km": "1270.00",
            "truck_type_id": 1,
            "currency": "EUR",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "viability_confirmed"
    assert response.json()["missing_fields"] is None
