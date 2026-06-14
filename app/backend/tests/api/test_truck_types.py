import pytest
from httpx import AsyncClient

from app.backend.db.session import get_async_session
from app.backend.models.truck_type import TruckType


@pytest.mark.asyncio
async def test_list_truck_types_returns_canonical_catalog_in_id_order(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/truck-types")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "name": "tautliner"},
        {"id": 2, "name": "reefer"},
        {"id": 3, "name": "mega"},
    ]


@pytest.mark.asyncio
async def test_list_truck_types_ignores_non_canonical_rows(
    client: AsyncClient,
) -> None:
    override_session = client._transport.app.dependency_overrides[get_async_session]
    session_generator = override_session()
    session = await anext(session_generator)

    try:
        session.add(TruckType(id=99, name="legacy-flatbed"))
        await session.commit()
    finally:
        await session_generator.aclose()

    response = await client.get("/api/v1/truck-types")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "name": "tautliner"},
        {"id": 2, "name": "reefer"},
        {"id": 3, "name": "mega"},
    ]
