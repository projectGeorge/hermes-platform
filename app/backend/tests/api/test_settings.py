import pytest


@pytest.mark.asyncio
async def test_get_runtime_settings_returns_stable_shape(auth_client) -> None:
    response = await auth_client.get("/api/v1/settings/runtime")
    assert response.status_code == 200
    data = response.json()

    assert "enable_auto_carrier_search" in data
    assert "enable_ingestion_smart_comms_handoff" in data
    assert "enable_smart_comms_retrieval" in data
    assert "enable_carrier_search_retrieval" in data
    assert "ingestion_provider" in data
    assert "ingestion_model_name" in data
    assert "reasoning_provider" in data
    assert "reasoning_model_name" in data
    assert "chroma_reachable" in data


@pytest.mark.asyncio
async def test_put_runtime_settings_updates_toggles(auth_client) -> None:
    response = await auth_client.put(
        "/api/v1/settings/runtime",
        json={"enable_auto_carrier_search": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enable_auto_carrier_search"] is True

    response = await auth_client.get("/api/v1/settings/runtime")
    data = response.json()
    assert data["enable_auto_carrier_search"] is True


@pytest.mark.asyncio
async def test_put_settings_persists_across_requests(auth_client) -> None:
    await auth_client.put(
        "/api/v1/settings/runtime",
        json={
            "enable_auto_carrier_search": True,
            "enable_ingestion_smart_comms_handoff": True,
        },
    )

    response = await auth_client.get("/api/v1/settings/runtime")
    data = response.json()
    assert data["enable_auto_carrier_search"] is True
    assert data["enable_ingestion_smart_comms_handoff"] is True
    assert data["enable_smart_comms_retrieval"] is False


@pytest.mark.asyncio
async def test_settings_endpoint_requires_auth(client) -> None:
    response = await client.get("/api/v1/settings/runtime")
    assert response.status_code == 401
