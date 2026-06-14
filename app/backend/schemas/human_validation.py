"""DTOs for Human-in-the-Loop load-order validation."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.backend.core.domain_enums import IngestionRunStatus
from app.backend.schemas.load_order import LoadOrderResponse


class HumanValidationLatestIngestionRunResponse(BaseModel):
    """Expose the latest persisted ingestion context for operator review."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    route: str
    status: IngestionRunStatus
    raw_text: str
    extracted_payload: dict[str, Any] | None
    execution_path: str | None = None
    provider: str | None = None
    model_name: str | None = None
    trace_steps: list[dict[str, object]] | None = None


class HumanValidationContextResponse(BaseModel):
    """Return the current human-validation state of an ingested order."""

    load_order: LoadOrderResponse
    latest_ingestion_run: HumanValidationLatestIngestionRunResponse
    missing_fields: dict[str, str]
    blocked_missing_fields: dict[str, str]
    reviewable_fields: list[str]
    can_confirm_viability: bool


class HumanValidationUpdateRequest(BaseModel):
    """Apply operator corrections to reviewable load-order fields."""

    reviewed_by_user_id: uuid.UUID
    customer_name: str | None = None
    origin_text: str | None = None
    destination_text: str | None = None
    origin_load_date: datetime | None = None
    destination_unload_date: datetime | None = None
    distance_km: Decimal | None = Field(default=None, ge=0)
    cargo_description: str | None = None
    weight_kg: Decimal | None = Field(default=None, ge=0)
    truck_type_id: int | None = None
    customer_price: Decimal | None = Field(default=None, ge=0)
    currency: Annotated[str | None, StringConstraints(min_length=3, max_length=3)] = None
    adr_required: bool | None = None
    review_notes: str | None = None


class HumanValidationUpdateRequestBrowser(BaseModel):
    """Apply operator corrections (browser-facing, no explicit operator ID)."""

    customer_name: str | None = None
    origin_text: str | None = None
    destination_text: str | None = None
    origin_load_date: datetime | None = None
    destination_unload_date: datetime | None = None
    distance_km: Decimal | None = Field(default=None, ge=0)
    cargo_description: str | None = None
    weight_kg: Decimal | None = Field(default=None, ge=0)
    truck_type_id: int | None = None
    customer_price: Decimal | None = Field(default=None, ge=0)
    currency: Annotated[str | None, StringConstraints(min_length=3, max_length=3)] = None
    adr_required: bool | None = None
    review_notes: str | None = None


class HumanValidationConfirmRequest(BaseModel):
    """Record the operator viability confirmation for an order."""

    reviewed_by_user_id: uuid.UUID
    review_notes: str | None = None


class HumanValidationConfirmRequestBrowser(BaseModel):
    """Record the operator viability confirmation (browser-facing, no explicit operator ID)."""

    review_notes: str | None = None
