from uuid import uuid4

from httpx import AsyncClient
import pytest


async def _create_order(
    client: AsyncClient,
    *,
    status: str = "viability_confirmed",
    customer_price: str = "1400.00",
    truck_type_id: int = 1,
    adr_required: bool = False,
) -> str:
    response = await client.post(
        "/api/v1/orders/",
        json={
            "status": status,
            "customer_name": "Acme Logistics",
            "origin_text": "Madrid, ES",
            "destination_text": "Paris, FR",
            "cargo_description": "Ceramic tiles",
            "weight_kg": "7800.00",
            "customer_price": customer_price,
            "distance_km": "1000.00",
            "truck_type_id": truck_type_id,
            "adr_required": adr_required,
            "currency": "EUR",
            "missing_fields": {},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_snapshot(
    client: AsyncClient,
    **order_kwargs: object,
) -> tuple[str, dict[str, object]]:
    order_id = await _create_order(client, **order_kwargs)
    response = await client.post(f"/api/v1/orders/{order_id}/carrier-search")
    assert response.status_code == 201
    return order_id, response.json()


def _get_rejected_trip_id(snapshot: dict[str, object]) -> str:
    rejected_trip_id = next(
        (
            item["trip_id"]
            for item in snapshot["candidates"]
            if item["proposal_status"] == "rejected"
        ),
        None,
    )
    assert rejected_trip_id is not None
    return rejected_trip_id


@pytest.mark.asyncio
async def test_put_carrier_selection_selects_candidate_and_marks_snapshot(
    auth_client: AsyncClient,
) -> None:
    order_id, snapshot = await _create_snapshot(auth_client)
    selected_trip_id = next(
        item["trip_id"] for item in snapshot["candidates"] if item["proposal_status"] == "candidate"
    )

    response = await auth_client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": selected_trip_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["load_order"]["status"] == "ready_for_formalization"
    assert body["load_order"]["selected_trip_id"] == selected_trip_id
    assert [item["trip_id"] for item in body["candidates"] if item["is_selected"]] == [
        selected_trip_id
    ]

    get_response = await auth_client.get(f"/api/v1/orders/{order_id}/carrier-candidates")
    detail_response = await auth_client.get(f"/api/v1/orders/{order_id}")
    reused_search_response = await auth_client.post(f"/api/v1/orders/{order_id}/carrier-search")

    assert get_response.status_code == 200
    assert get_response.json()["load_order"]["selected_trip_id"] == selected_trip_id
    assert [
        item["trip_id"]
        for item in get_response.json()["candidates"]
        if item["is_selected"]
    ] == [selected_trip_id]
    assert detail_response.status_code == 200
    assert detail_response.json()["selected_trip_id"] == selected_trip_id
    assert reused_search_response.status_code == 200
    assert reused_search_response.json()["load_order"]["selected_trip_id"] == selected_trip_id
    assert [
        item["trip_id"]
        for item in reused_search_response.json()["candidates"]
        if item["is_selected"]
    ] == [selected_trip_id]


@pytest.mark.asyncio
async def test_put_carrier_selection_reselects_other_candidate(
    auth_client: AsyncClient,
) -> None:
    order_id, snapshot = await _create_snapshot(auth_client)
    candidate_trip_ids = [
        item["trip_id"] for item in snapshot["candidates"] if item["proposal_status"] == "candidate"
    ]
    first_trip_id, second_trip_id = candidate_trip_ids[:2]

    first_response = await auth_client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": first_trip_id},
    )
    second_response = await auth_client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": second_trip_id},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["load_order"]["selected_trip_id"] == second_trip_id
    assert [
        item["trip_id"]
        for item in second_response.json()["candidates"]
        if item["is_selected"]
    ] == [second_trip_id]


@pytest.mark.asyncio
async def test_put_carrier_selection_allows_clearing_selected_trip(
    auth_client: AsyncClient,
) -> None:
    order_id, snapshot = await _create_snapshot(auth_client)
    selected_trip_id = next(
        item["trip_id"] for item in snapshot["candidates"] if item["proposal_status"] == "candidate"
    )

    select_response = await auth_client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": selected_trip_id},
    )
    clear_response = await auth_client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": None},
    )

    assert select_response.status_code == 200
    assert clear_response.status_code == 200
    assert clear_response.json()["load_order"]["status"] == "searching_carrier"
    assert clear_response.json()["load_order"]["selected_trip_id"] is None
    assert [
        item["trip_id"]
        for item in clear_response.json()["candidates"]
        if item["is_selected"]
    ] == []


@pytest.mark.asyncio
async def test_put_carrier_selection_rejects_rejected_trip(
    auth_client: AsyncClient,
) -> None:
    order_id, snapshot = await _create_snapshot(
        auth_client,
        customer_price="800.00",
        adr_required=True,
    )
    rejected_trip_id = _get_rejected_trip_id(snapshot)

    response = await auth_client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": rejected_trip_id},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Carrier selection requires a candidate trip"


@pytest.mark.asyncio
async def test_put_carrier_selection_returns_404_without_snapshot(
    auth_client: AsyncClient,
) -> None:
    order_id = await _create_order(auth_client)

    response = await auth_client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": str(uuid4())},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Load order has no carrier-search snapshot"


@pytest.mark.asyncio
async def test_formalize_requires_selected_trip_after_search(
    auth_client: AsyncClient,
) -> None:
    order_id, _ = await _create_snapshot(auth_client)

    response = await auth_client.post(f"/api/v1/orders/{order_id}/formalize")

    assert response.status_code == 409
    assert response.json()["detail"] == "Carrier selection required before ready_for_formalization"


@pytest.mark.asyncio
async def test_update_ready_for_formalization_requires_selected_trip_after_search(
    auth_client: AsyncClient,
) -> None:
    order_id, _ = await _create_snapshot(auth_client)

    response = await auth_client.put(
        f"/api/v1/orders/{order_id}",
        json={"status": "ready_for_formalization"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Carrier selection required before ready_for_formalization"


# --- Protected browser contract tests ---

@pytest.mark.asyncio
async def test_put_carrier_selection_with_auth_works_on_protected_router(
    auth_client: AsyncClient,
) -> None:
    order_id, snapshot = await _create_snapshot(auth_client)
    selected_trip_id = next(
        item["trip_id"] for item in snapshot["candidates"] if item["proposal_status"] == "candidate"
    )

    response = await auth_client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": selected_trip_id},
    )

    assert response.status_code == 200
    assert response.json()["load_order"]["status"] == "ready_for_formalization"


@pytest.mark.asyncio
async def test_formalize_promotes_ready_for_formalization_to_formalized(
    auth_client: AsyncClient,
) -> None:
    order_id, snapshot = await _create_snapshot(auth_client)
    selected_trip_id = next(
        item["trip_id"] for item in snapshot["candidates"] if item["proposal_status"] == "candidate"
    )

    selection_response = await auth_client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": selected_trip_id},
    )
    assert selection_response.status_code == 200

    response = await auth_client.post(f"/api/v1/orders/{order_id}/formalize")

    assert response.status_code == 200
    assert response.json()["status"] == "formalized"


@pytest.mark.asyncio
async def test_put_carrier_selection_without_auth_is_rejected(
    client: AsyncClient,
    auth_client: AsyncClient,
) -> None:
    order_id, snapshot = await _create_snapshot(auth_client)
    selected_trip_id = next(
        item["trip_id"] for item in snapshot["candidates"] if item["proposal_status"] == "candidate"
    )

    response = await client.put(
        f"/api/v1/orders/{order_id}/carrier-selection",
        json={"trip_id": selected_trip_id},
    )

    assert response.status_code == 401
