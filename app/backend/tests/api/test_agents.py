"""API tests for the agents endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_agent_statuses_returns_empty_state(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/agents/status")

    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert len(data["agents"]) == 5
    agent_kinds = {a["agent_kind"] for a in data["agents"]}
    assert agent_kinds == {"orchestrator", "ingestion", "carrier_search", "smart_comms", "monitoring"}


@pytest.mark.asyncio
async def test_get_agent_statuses_shows_activity_after_order_creation(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "cargo_description": "Test cargo",
            "customer_price": "500.00",
            "currency": "EUR",
        },
    )
    assert create_response.status_code == 201

    status_response = await auth_client.get("/api/v1/agents/status")
    assert status_response.status_code == 200

    orchestrator = next(
        a for a in status_response.json()["agents"] if a["agent_kind"] == "orchestrator"
    )
    assert orchestrator["last_activity_at"] is not None
    assert orchestrator["headline"] is not None


@pytest.mark.asyncio
async def test_get_orchestrator_timeline_returns_empty_initially(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/api/v1/agents/orchestrator/timeline")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_orchestrator_timeline_shows_order_creation(
    auth_client: AsyncClient,
) -> None:
    create_response = await auth_client.post(
        "/api/v1/orders/",
        json={
            "status": "viability_pending",
            "cargo_description": "Test cargo",
            "customer_price": "500.00",
            "currency": "EUR",
        },
    )
    assert create_response.status_code == 201

    timeline_response = await auth_client.get("/api/v1/agents/orchestrator/timeline")
    assert timeline_response.status_code == 200

    timeline = timeline_response.json()
    assert len(timeline) >= 1
    assert any("order" in item["title"].lower() for item in timeline)


@pytest.mark.asyncio
async def test_get_orchestrator_timeline_respects_limit(auth_client: AsyncClient) -> None:
    for i in range(3):
        await auth_client.post(
            "/api/v1/orders/",
            json={
                "status": "viability_pending",
                "cargo_description": f"Test cargo {i}",
                "customer_price": "500.00",
                "currency": "EUR",
            },
        )

    response = await auth_client.get("/api/v1/agents/orchestrator/timeline?limit=2")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_agents_endpoints_require_authentication(client: AsyncClient) -> None:
    status_response = await client.get("/api/v1/agents/status")
    assert status_response.status_code == 401 or status_response.status_code == 403

    timeline_response = await client.get("/api/v1/agents/orchestrator/timeline")
    assert timeline_response.status_code == 401 or timeline_response.status_code == 403
