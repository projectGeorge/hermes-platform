import pytest
from httpx import AsyncClient


SEEDED_USER_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_get_human_validation_context_returns_ingestion_review_state(
    auth_client: AsyncClient,
) -> None:
    ingestion_response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                ]
            ),
        },
    )
    order_id = ingestion_response.json()["load_order"]["id"]

    response = await auth_client.get(f"/api/v1/orders/{order_id}/human-validation")

    assert response.status_code == 200
    body = response.json()
    assert body["load_order"]["status"] == "viability_pending"
    assert body["missing_fields"] == {
        "weight_kg": "not_found",
        "customer_price": "not_found",
    }
    assert body["blocked_missing_fields"] == {}
    assert body["latest_ingestion_run"]["route"] == "load_order_ingestion"
    assert "Customer: Acme Logistics" in body["latest_ingestion_run"]["raw_text"]
    assert body["can_confirm_viability"] is False


@pytest.mark.asyncio
async def test_put_human_validation_updates_order_and_post_confirm_transitions_to_viability_confirmed(
    auth_client: AsyncClient,
) -> None:
    ingestion_response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                ]
            ),
        },
    )
    order_id = ingestion_response.json()["load_order"]["id"]

    update_response = await auth_client.put(
        f"/api/v1/orders/{order_id}/human-validation",
        json={
            "weight_kg": "7800.00",
            "customer_price": "1250.50",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["load_order"]["status"] == "viability_pending"
    assert update_response.json()["missing_fields"] == {}
    assert update_response.json()["can_confirm_viability"] is True

    confirm_response = await auth_client.post(
        f"/api/v1/orders/{order_id}/confirm-viability",
        json={},
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "viability_confirmed"

    detail_response = await auth_client.get(f"/api/v1/orders/{order_id}")

    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "viability_confirmed"


@pytest.mark.asyncio
async def test_human_validation_requires_distance_before_confirming_viability(
    auth_client: AsyncClient,
) -> None:
    ingestion_response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                    "Weight: 7800",
                    "Price: 1250.50 EUR",
                ]
            ),
        },
    )
    order_id = ingestion_response.json()["load_order"]["id"]

    context_response = await auth_client.get(f"/api/v1/orders/{order_id}/human-validation")

    assert context_response.status_code == 200
    assert context_response.json()["missing_fields"] == {}
    assert context_response.json()["can_confirm_viability"] is True

    carrier_search_response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    assert carrier_search_response.status_code == 409
    assert carrier_search_response.json()["detail"] == "Carrier search not allowed for status: viability_pending"


@pytest.mark.asyncio
async def test_confirm_viability_promotes_complete_pending_ingestion_manual_order(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "pending_ingestion",
            "customer_name": "Manual Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "origin_load_date": "2026-05-04T09:30:00",
            "cargo_description": "Manual order",
            "weight_kg": "7800.00",
            "customer_price": "1250.50",
            "distance_km": "1270.00",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    confirm_response = await auth_client.post(
        f"/api/v1/orders/{order_id}/confirm-viability",
        json={},
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "viability_confirmed"


@pytest.mark.asyncio
async def test_human_validation_creates_manual_review_context_without_ingestion_run(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "pending_ingestion",
            "customer_name": "Manual Logistics",
            "origin_text": "Madrid, ES",
            "cargo_description": "Manual order",
            "currency": "EUR",
        },
    )
    order_id = create_response.json()["id"]

    response = await auth_client.get(f"/api/v1/orders/{order_id}/human-validation")

    assert response.status_code == 200
    body = response.json()
    assert body["load_order"]["status"] == "pending_ingestion"
    assert body["latest_ingestion_run"]["route"] == "manual_order_review"
    assert body["latest_ingestion_run"]["execution_path"] == "manual"
    assert "Manual Logistics" in body["latest_ingestion_run"]["raw_text"]
    assert body["can_confirm_viability"] is False


@pytest.mark.asyncio
async def test_confirm_viability_returns_422_when_missing_fields_remain(
    auth_client: AsyncClient,
) -> None:
    ingestion_response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                ]
            ),
        },
    )
    order_id = ingestion_response.json()["load_order"]["id"]

    response = await auth_client.post(
        f"/api/v1/orders/{order_id}/confirm-viability",
        json={},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Cannot confirm viability while missing_fields remain"


@pytest.mark.asyncio
async def test_put_human_validation_completes_pending_ingestion_when_textual_gap_is_filled(
    auth_client: AsyncClient,
) -> None:
    ingestion_response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                ]
            ),
        },
    )
    order_id = ingestion_response.json()["load_order"]["id"]

    update_response = await auth_client.put(
        f"/api/v1/orders/{order_id}/human-validation",
        json={
            "destination_text": "Paris, FR",
            "weight_kg": "7800.00",
            "customer_price": "1250.50",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["load_order"]["status"] == "viability_pending"
    assert update_response.json()["load_order"]["destination_text"] == "Paris, FR"
    assert update_response.json()["missing_fields"] == {}
    assert update_response.json()["blocked_missing_fields"] == {}
    assert update_response.json()["can_confirm_viability"] is True


# --- Protected browser contract tests ---

@pytest.mark.asyncio
async def test_put_human_validation_with_auth_succeeds_without_explicit_user_id(
    auth_client: AsyncClient,
) -> None:
    ingestion_response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                ]
            ),
        },
    )
    order_id = ingestion_response.json()["load_order"]["id"]

    update_response = await auth_client.put(
        f"/api/v1/orders/{order_id}/human-validation",
        json={
            "weight_kg": "7800.00",
            "customer_price": "1250.50",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["missing_fields"] == {}
    assert update_response.json()["can_confirm_viability"] is True


@pytest.mark.asyncio
async def test_confirm_viability_with_auth_succeeds_without_explicit_user_id(
    auth_client: AsyncClient,
) -> None:
    ingestion_response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                    "Weight: 7800",
                    "Price: 1250.50",
                ]
            ),
        },
    )
    order_id = ingestion_response.json()["load_order"]["id"]

    confirm_response = await auth_client.post(
        f"/api/v1/orders/{order_id}/confirm-viability",
        json={},
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "viability_confirmed"


@pytest.mark.asyncio
async def test_put_human_validation_without_auth_is_rejected(
    client: AsyncClient,
    auth_client: AsyncClient,
) -> None:
    ingestion_response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                ]
            ),
        },
    )
    order_id = ingestion_response.json()["load_order"]["id"]

    response = await client.put(
        f"/api/v1/orders/{order_id}/human-validation",
        json={
            "weight_kg": "7800.00",
            "customer_price": "1250.50",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_confirm_viability_without_auth_is_rejected(
    client: AsyncClient,
    auth_client: AsyncClient,
) -> None:
    ingestion_response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                    "Weight: 7800",
                    "Price: 1250.50",
                ]
            ),
        },
    )
    order_id = ingestion_response.json()["load_order"]["id"]

    response = await client.post(
        f"/api/v1/orders/{order_id}/confirm-viability",
        json={},
    )

    assert response.status_code == 401
