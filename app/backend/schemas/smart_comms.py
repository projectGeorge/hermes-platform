"""DTOs for Smart Comms conversations and messages."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.backend.core.domain_enums import SmartCommsContextType, SmartCommsMessageRole


def _to_utc_iso(v: datetime | None) -> str | None:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


class SmartCommsResolveRequest(BaseModel):
    context_type: SmartCommsContextType
    context_id: uuid.UUID | None = None
    route_path: str


class SmartCommsMessageRequest(BaseModel):
    content: str


class SmartCommsConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    context_type: SmartCommsContextType
    context_id: uuid.UUID | None
    route_path: str
    title: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)


class SmartCommsMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: SmartCommsMessageRole
    content: str
    metadata: dict[str, object] | None = Field(validation_alias="extra_metadata")
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _to_utc_iso(v)
