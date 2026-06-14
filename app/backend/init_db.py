from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.backend.db import Base, engine
import app.backend.models  # noqa: F401  # registra todos los modelos en Base.metadata


BASE_DIR = Path(__file__).resolve().parents[2]


def init_models() -> None:
    alembic_config = Config(str(BASE_DIR / "alembic.ini"))
    command.upgrade(alembic_config, "head")


async def main() -> None:
    try:
        init_models()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
