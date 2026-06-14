from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backend.core.settings import get_settings


settings = get_settings()

engine = create_async_engine(
    settings.async_database_url,
    echo=False,  # Cambiar a True para debug SQL
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


# Type alias para inyección de dependencias en FastAPI
AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]
