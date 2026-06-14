"""Bounded DTOs for delegated orchestrator actions."""

import uuid
from typing import Literal

from pydantic import BaseModel, StringConstraints
from typing import Annotated

from app.backend.schemas.agents import AgentActivityResponse
from app.backend.schemas.ingestion import LoadOrderIngestionResponse
from app.backend.schemas.monitoring import ExecutionMonitoringReadModelResponse
from app.backend.schemas.smart_comms import SmartCommsConversationResponse


DelegatedActionKind = Literal[
    "extract_email_into_order_draft",
    "draft_message",
    "open_shipment_monitoring",
    "run_carrier_search",
]


class OrchestratorDelegationRequest(BaseModel):
    action: DelegatedActionKind
    load_order_id: uuid.UUID | None = None
    source_email_text: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1)] = None


class OrchestratorDelegationResponse(BaseModel):
    delegated_to: Literal["ingestion", "smart_comms", "monitoring", "carrier_search"]
    activity: AgentActivityResponse
    ingestion_result: LoadOrderIngestionResponse | None = None
    smart_comms_conversation: SmartCommsConversationResponse | None = None
    monitoring_snapshot: ExecutionMonitoringReadModelResponse | None = None
