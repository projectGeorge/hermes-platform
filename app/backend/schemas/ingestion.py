import uuid
from typing import Any

from pydantic import BaseModel, StringConstraints
from typing import Annotated

from app.backend.core.domain_enums import IngestionRunStatus
from app.backend.schemas.load_order import LoadOrderResponse


class IngestionLoadOrderRequest(BaseModel):
    user_id: uuid.UUID
    raw_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class IngestionLoadOrderRequestBrowser(BaseModel):
    raw_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LoadOrderIngestionResponse(BaseModel):
    """Result returned by the load order ingestion service."""

    ingestion_run_id: uuid.UUID
    route: str
    run_status: IngestionRunStatus
    load_order: LoadOrderResponse
    extracted_payload: dict[str, Any]
    missing_fields: dict[str, str]
    execution_path: str | None = None
    provider: str | None = None
    model_name: str | None = None
    trace_steps: list[dict[str, object]] | None = None
