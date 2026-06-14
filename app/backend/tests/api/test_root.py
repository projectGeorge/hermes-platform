import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://hermes_user:hermes_password@localhost:5432/hermes_db",
)

from app.backend.main import create_app


@pytest.mark.asyncio
async def test_root_returns_api_status() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "Hermes API is running!",
    }
