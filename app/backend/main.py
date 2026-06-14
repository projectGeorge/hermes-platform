API_V1_PREFIX = "/api/v1"
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.backend.api.endpoints.agents import router as agents_router
from app.backend.api.endpoints.ingestion import router as ingestion_router
from app.backend.api.endpoints.monitoring import router as monitoring_router
from app.backend.api.endpoints.orders import router as orders_router
from app.backend.api.endpoints.settings import router as settings_router
from app.backend.api.endpoints.smart_comms import router as smart_comms_router
from app.backend.api.endpoints.truck_types import router as truck_types_router
from app.backend.api.endpoints.users import router as users_router
from app.backend.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Hermes API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(users_router, prefix=API_V1_PREFIX)
    app.include_router(orders_router, prefix=API_V1_PREFIX)
    app.include_router(ingestion_router, prefix=API_V1_PREFIX)
    app.include_router(truck_types_router, prefix=API_V1_PREFIX)
    app.include_router(agents_router, prefix=API_V1_PREFIX)
    app.include_router(monitoring_router, prefix=API_V1_PREFIX)
    app.include_router(settings_router, prefix=API_V1_PREFIX)
    app.include_router(smart_comms_router, prefix=API_V1_PREFIX)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "ok", "message": "Hermes API is running!"}

    return app


app = create_app()
