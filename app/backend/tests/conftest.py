import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app/backend/tests/bootstrap.db")
os.environ["INGESTION_MODEL_NAME"] = ""
os.environ["LOCAL_AGENT_MODEL_NAME"] = ""
os.environ["REASONING_MODEL_NAME"] = ""

import app.backend.models  # noqa: F401
from app.backend.db.base import Base
from app.backend.db.session import get_async_session, AsyncSessionDep
from app.backend.api.dependencies.auth import get_current_user
from app.backend.main import create_app
from app.backend.models.user import User

SEEDED_USER_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    test_database_path = tmp_path / "test.db"
    test_database_url = f"sqlite+aiosqlite:///{test_database_path.as_posix()}"

    engine = create_async_engine(test_database_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add(
            User(
                id=SEEDED_USER_ID,
                email="operator@example.com",
                operator_name="Operator Demo",
                auth_id="auth_demo",
            )
        )
        await session.commit()

    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def auth_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    test_database_path = tmp_path / "test.db"
    test_database_url = f"sqlite+aiosqlite:///{test_database_path.as_posix()}"

    engine = create_async_engine(test_database_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        existing = await session.get(User, SEEDED_USER_ID)
        if existing is None:
            session.add(
                User(
                    id=SEEDED_USER_ID,
                    email="operator@example.com",
                    operator_name="Operator Demo",
                    auth_id="auth_demo",
                )
            )
            await session.commit()

    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    async def override_get_current_user(session: AsyncSessionDep) -> User:
        user = await session.get(User, SEEDED_USER_ID)
        return user

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def order_payload(client: AsyncClient) -> dict[str, object]:
    return {
        "user_id": str(SEEDED_USER_ID),
        "status": "viability_pending",
        "cargo_description": "Palets de producto seco",
        "weight_kg": "1200.00",
        "customer_price": "950.00",
        "currency": "EUR",
    }
