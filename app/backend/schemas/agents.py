"""DTOs for agent activity and status read models."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.backend.core.domain_enums import AgentActivityState, AgentKind


def _to_utc_iso(v: datetime | None) -> str | None:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


class AgentActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_kind: AgentKind
    activity_state: AgentActivityState
    load_order_id: uuid.UUID | None
    title: str
    detail: str | None
    activity_key: str
    next_action: str | None
    metadata: dict[str, object] | None = Field(validation_alias="extra_metadata")
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)


class AgentStatusResponse(BaseModel):
    agent_kind: AgentKind
    display_name: str
    state: AgentActivityState
    headline: str
    last_activity_at: datetime | None
    active_item_count: int

    @field_serializer("last_activity_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)


class AgentStatusListResponse(BaseModel):
    agents: list[AgentStatusResponse]


class OrchestratorTimelineItem(BaseModel):
    agent: AgentKind
    title: str
    detail: str | None
    next_action: str | None
    load_order_id: uuid.UUID | None
    customer_name: str | None
    route_summary: str | None
    order_status: str | None
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)
