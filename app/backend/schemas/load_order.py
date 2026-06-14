import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer

from app.backend.core.domain_enums import LoadOrderStatus


def _to_utc_iso(v: datetime | None) -> str | None:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


class LoadOrderCreate(BaseModel):
    user_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    status: LoadOrderStatus = LoadOrderStatus.PENDING_INGESTION

    origin_id: uuid.UUID | None = None
    origin_text: str | None = None
    origin_load_date: datetime | None = None
    destination_id: uuid.UUID | None = None
    destination_text: str | None = None
    destination_unload_date: datetime | None = None
    distance_km: Decimal | None = Field(default=None, ge=0)

    cargo_description: str | None = None
    weight_kg: Decimal | None = Field(default=None, ge=0)
    truck_type_id: int | None = None
    adr_required: bool = False
    missing_fields: dict[str, Any] | None = None

    customer_price: Decimal | None = Field(default=None, ge=0)
    currency: Annotated[str, StringConstraints(min_length=3, max_length=3)] = "EUR"


class LoadOrderCreateRequest(BaseModel):
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    status: LoadOrderStatus = LoadOrderStatus.PENDING_INGESTION

    origin_id: uuid.UUID | None = None
    origin_text: str | None = None
    origin_load_date: datetime | None = None
    destination_id: uuid.UUID | None = None
    destination_text: str | None = None
    destination_unload_date: datetime | None = None
    distance_km: Decimal | None = Field(default=None, ge=0)

    cargo_description: str | None = None
    weight_kg: Decimal | None = Field(default=None, ge=0)
    truck_type_id: int | None = None
    adr_required: bool = False
    missing_fields: dict[str, Any] | None = None

    customer_price: Decimal | None = Field(default=None, ge=0)
    currency: Annotated[str, StringConstraints(min_length=3, max_length=3)] = "EUR"


class LoadOrderUpdate(BaseModel):
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    status: LoadOrderStatus | None = None

    origin_id: uuid.UUID | None = None
    origin_text: str | None = None
    origin_load_date: datetime | None = None
    destination_id: uuid.UUID | None = None
    destination_text: str | None = None
    destination_unload_date: datetime | None = None
    distance_km: Decimal | None = Field(default=None, ge=0)

    cargo_description: str | None = None
    weight_kg: Decimal | None = Field(default=None, ge=0)
    truck_type_id: int | None = None
    adr_required: bool | None = None
    missing_fields: dict[str, Any] | None = None

    customer_price: Decimal | None = Field(default=None, ge=0)
    currency: Annotated[str | None, StringConstraints(min_length=3, max_length=3)] = None


class LoadOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    customer_id: uuid.UUID | None
    customer_name: str | None
    status: LoadOrderStatus
    selected_trip_id: uuid.UUID | None

    origin_id: uuid.UUID | None
    origin_text: str | None
    origin_load_date: datetime | None
    destination_id: uuid.UUID | None
    destination_text: str | None
    destination_unload_date: datetime | None
    distance_km: Decimal | None

    cargo_description: str | None
    weight_kg: Decimal | None
    truck_type_id: int | None
    adr_required: bool
    missing_fields: dict[str, Any] | None

    customer_price: Decimal | None
    currency: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("origin_load_date", "destination_unload_date", "created_at", "updated_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)


class LoadOrderListPageResponse(BaseModel):
    items: list[LoadOrderResponse]
    total: int
    skip: int
    limit: int


class DashboardLoadOrderItem(BaseModel):
    id: uuid.UUID
    customer_name: str | None
    status: LoadOrderStatus
    origin_text: str | None
    destination_text: str | None
    updated_at: datetime

    @field_serializer("updated_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)


class DashboardLoadOrderSummaryResponse(BaseModel):
    active_order_count: int
    needs_attention_count: int
    attention_orders: list[DashboardLoadOrderItem]
    recent_active_orders: list[DashboardLoadOrderItem]
