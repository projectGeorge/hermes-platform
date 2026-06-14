import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_users_returns_seeded_operator(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/")

    assert response.status_code == 200
    assert response.json()[0]["email"] == "operator@example.com"
