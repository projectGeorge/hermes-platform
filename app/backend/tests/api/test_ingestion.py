import pytest
from httpx import AsyncClient

from app.backend.core.domain_enums import SmartCommsContextType


@pytest.mark.asyncio
async def test_ingest_load_order_creates_viability_pending_order(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                    "Price: 1250.50",
                    "Weight: 7800",
                    "ADR: yes",
                ]
            ),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["route"] == "load_order_ingestion"
    assert body["run_status"] == "completed"
    assert body["load_order"]["status"] == "viability_pending"
    assert body["load_order"]["customer_name"] == "Acme Logistics"
    assert body["load_order"]["origin_text"] == "Madrid, ES"
    assert body["load_order"]["destination_text"] == "Paris, FR"
    assert body["missing_fields"] == {}
    assert body["extracted_payload"]["customer_name"] == "Acme Logistics"
    assert "execution_path" in body
    assert isinstance(body["execution_path"], str)


@pytest.mark.asyncio
async def test_ingest_load_order_falls_back_to_pending_ingestion(
    auth_client: AsyncClient,
) -> None:
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
    body = response.json()
    assert body["load_order"]["status"] == "pending_ingestion"
    assert body["load_order"]["customer_name"] == "Acme Logistics"
    assert body["load_order"]["origin_text"] == "Madrid, ES"
    assert body["load_order"]["destination_text"] is None
    assert body["missing_fields"] == {
        "destination_text": "not_found",
        "origin_load_date": "not_found",
        "customer_price": "not_found",
        "weight_kg": "not_found",
    }


@pytest.mark.asyncio
async def test_ingest_load_order_rejects_blank_raw_text(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "   \n\t  ",
        },
    )

    assert response.status_code == 422

    orders_response = await auth_client.get("/api/v1/orders/")

    assert orders_response.status_code == 200
    assert orders_response.json() == []


# --- Protected browser contract tests ---

@pytest.mark.asyncio
async def test_ingest_load_order_with_auth_succeeds_without_explicit_user_id(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Customer: Acme Logistics",
                    "Origin: Madrid, ES",
                    "Destination: Paris, FR",
                    "Load Date: 2026-05-04 09:30",
                    "Cargo: Ceramic tiles",
                    "Price: 1250.50",
                    "Weight: 7800",
                    "ADR: yes",
                ]
            ),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["load_order"]["status"] == "viability_pending"
    assert body["load_order"]["customer_name"] == "Acme Logistics"


@pytest.mark.asyncio
async def test_ingest_load_order_infers_company_name_and_truck_type_from_operational_email(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/ingestion/load-orders",
        json={
            "raw_text": "\n".join(
                [
                    "Asunto: Nueva orden de transporte - Sevilla a Rotterdam",
                    "",
                    "Hola, equipo:",
                    "Origen: Sevilla, ES",
                    "Destino: Rotterdam, NL",
                    "Fecha de carga: 2026-05-04 09:30",
                    "Descripcion de la carga: Palets de producto quimico de limpieza",
                    "Tipo de camión: tautliner",
                    "",
                    "Saludos cordiales,",
                    "Carmen Ortiz",
                    "Export Manager | SurQuimica Global S.L.",
                ]
            ),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["load_order"]["customer_name"] == "SurQuimica Global S.L."
    assert body["load_order"]["truck_type_id"] == 1


@pytest.mark.asyncio
async def test_ingest_load_order_without_auth_is_rejected(
    client: AsyncClient,
) -> None:
    response = await client.post(
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

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ingest_load_order_hands_off_to_smart_comms_when_enabled(
    auth_client: AsyncClient,
) -> None:
    settings_response = await auth_client.put(
        "/api/v1/settings/runtime",
        json={"enable_ingestion_smart_comms_handoff": True},
    )
    assert settings_response.status_code == 200

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
    body = response.json()
    order_id = body["load_order"]["id"]

    conversation_response = await auth_client.post(
        "/api/v1/smart-comms/conversations/resolve",
        json={
            "context_type": SmartCommsContextType.LOAD_ORDER,
            "context_id": order_id,
            "route_path": f"/orders/{order_id}",
        },
    )
    assert conversation_response.status_code == 200
    conversation_id = conversation_response.json()["id"]

    messages_response = await auth_client.get(
        f"/api/v1/smart-comms/conversations/{conversation_id}/messages"
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    assert "could not confidently complete the intake draft" in messages[0]["content"].lower()
    assert "destination" in messages[0]["content"].lower()
    assert "load date" in messages[0]["content"].lower()
    assert "customer" not in messages[0]["content"].lower()
