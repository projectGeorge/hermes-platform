"""DTOs for execution monitoring read models."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.backend.core.domain_enums import ExecutionMonitoringStatus


def _to_utc_iso(v: datetime | None) -> str | None:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


class ExecutionMonitoringCoordinate(BaseModel):
    lat: float
    lng: float


class ExecutionMonitoringPosition(BaseModel):
    label: str
    lat: float
    lng: float
    progress_percent: int


class ExecutionMonitoringRoutePoint(BaseModel):
    kind: str
    label: str
    sequence: int
    lat: float
    lng: float
    status: str = "pending"


class ExecutionMonitoringEvent(BaseModel):
    event_type: str
    title: str
    detail: str | None = None
    checkpoint_name: str | None = None
    occurred_at: datetime
    severity: str = "info"

    @field_serializer("occurred_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)


class ExecutionMonitoringAlert(BaseModel):
    id: str
    load_order_id: str | None = None
    alert_type: str
    title: str
    detail: str | None = None
    severity: str = "info"
    status: str = "open"
    dedupe_key: str
    metadata: dict[str, object] | None = None
    created_at: datetime
    resolved_at: datetime | None = None

    @field_serializer("created_at", "resolved_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)


class ExecutionMonitoringSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    load_order_id: uuid.UUID
    status: ExecutionMonitoringStatus
    progress_percent: int
    current_checkpoint: str | None
    route_points: list[ExecutionMonitoringRoutePoint]
    route_path: list[ExecutionMonitoringCoordinate]
    current_position: ExecutionMonitoringPosition
    events: list[ExecutionMonitoringEvent]
    alerts: list[ExecutionMonitoringAlert]
    metadata: dict[str, object] | None = Field(validation_alias="extra_metadata")
    created_at: datetime
    last_refreshed_at: datetime

    @field_serializer("created_at", "last_refreshed_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)


class ExecutionMonitoringShipmentSummary(BaseModel):
    route_label: str
    customer_name: str | None = None
    cargo_description: str | None = None
    carrier_name: str | None = None
    distance_km: float | None = None
    current_status_label: str
    last_update_source: str


class ExecutionMonitoringAgentUpdate(BaseModel):
    source: str = "deterministic"
    summary: str
    operator_note: str | None = None
    incident_summary: str | None = None
    generated_at: datetime

    @field_serializer("generated_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)


class ExecutionMonitoringReadModelResponse(BaseModel):
    snapshot: ExecutionMonitoringSnapshotResponse
    alerts: list[ExecutionMonitoringAlert]
    shipment: ExecutionMonitoringShipmentSummary
    agent_update: ExecutionMonitoringAgentUpdate
