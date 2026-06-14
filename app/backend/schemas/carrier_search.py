"""DTOs for persisted carrier-search snapshots and selection."""

import uuid
from decimal import Decimal

from pydantic import BaseModel

from app.backend.core.domain_enums import CarrierRejectionReason, TripProposalStatus
from app.backend.schemas.load_order import LoadOrderResponse


class CarrierSelectionRequest(BaseModel):
    trip_id: uuid.UUID | None = None


class CarrierCandidateResponse(BaseModel):
    trip_id: uuid.UUID
    carrier_id: uuid.UUID
    company_name: str
    truck_type_id: int | None
    reliability_rating: Decimal | None
    documentation_valid: bool
    adr_capable: bool
    base_price_km: Decimal | None
    carrier_price: Decimal | None
    profit_margin: Decimal | None
    proposal_status: TripProposalStatus
    ai_rejection_reason: CarrierRejectionReason | None
    is_selected: bool = False
    ranking_score: Decimal | None = None
    score_breakdown: dict[str, object] | None = None
    agent_reasoning: str | None = None


class CarrierSearchResponse(BaseModel):
    load_order: LoadOrderResponse
    candidates: list[CarrierCandidateResponse]
