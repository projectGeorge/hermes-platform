"""Services for intelligent carrier-search snapshots with scoring and reasoning."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.backend.core.domain_enums import (
    CarrierPricingModel,
    CarrierRejectionReason,
    LoadOrderStatus,
    TripProposalStatus,
    validate_load_order_transition,
)
from app.backend.core.settings import Settings
from app.backend.models.carrier import Carrier
from app.backend.models.load_order import LoadOrder
from app.backend.models.trip import Trip
from app.backend.schemas.carrier_search import CarrierCandidateResponse, CarrierSearchResponse
from app.backend.schemas.load_order import LoadOrderResponse
from app.backend.services.carrier_catalog import CANONICAL_CARRIERS, CanonicalCarrier
from app.backend.services.prototype_catalog import ensure_canonical_prototype_truck_types

logger = logging.getLogger(__name__)


class CarrierEvaluation(BaseModel):
    carrier_id: str
    proposal_status: str
    rejection_reason: str | None = None
    ranking_score: float = Field(default=0.0, ge=0.0, le=100.0)
    score_breakdown: dict[str, float] = {}
    agent_reasoning: str = ""

    model_config = {"extra": "forbid"}

    @field_validator("proposal_status")
    @classmethod
    def _validate_proposal_status(cls, value: str) -> str:
        if value not in {"candidate", "rejected"}:
            raise ValueError("proposal_status must be 'candidate' or 'rejected'")
        return value

    @field_validator("rejection_reason")
    @classmethod
    def _validate_rejection_reason(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in {
            "invalid_documentation",
            "adr_not_supported",
            "truck_type_mismatch",
            "non_profitable",
        }:
            raise ValueError("Invalid rejection reason")
        return value


class CarrierEvaluationList(BaseModel):
    candidates: list[CarrierEvaluation] = []

    model_config = {"extra": "forbid"}


def _validate_carrier_evaluation(raw: dict) -> CarrierEvaluationList:
    try:
        return CarrierEvaluationList(**raw)
    except Exception:
        return CarrierEvaluationList(candidates=[])


async def _evaluate_carriers_with_reasoning(
    *,
    settings: Settings,
    order_context: str,
    carrier_names: list[str],
) -> CarrierEvaluationList:
    from app.backend.services.model_runtime_gateway import structured_completion

    carrier_list = "\n".join(f"- {name}" for name in carrier_names)

    result = await structured_completion(
        settings=settings,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a freight carrier evaluator. Given an order context and a list of "
                    "carrier names, evaluate each carrier for fit. Return valid JSON with an object "
                    'containing "candidates": an array of objects with keys: carrier_id (string, '
                    "use lowercase-with-hyphens format matching the carrier name), "
                    "proposal_status ('candidate' or 'rejected'), rejection_reason (null or string: "
                    "invalid_documentation, adr_not_supported, truck_type_mismatch, non_profitable), "
                    "ranking_score (float 0-100), score_breakdown (object with route_match, "
                    "price_competitiveness, reliability, truck_adr_compatibility as floats), "
                    "agent_reasoning (string explaining the evaluation). "
                    "Rank candidates by best fit first. Include ALL provided carrier names. "
                    "Evaluate every carrier even if their region differs from the route. "
                    "Use only the provided order context and retrieved historical notes if present. "
                    "Do not invent certifications, prices, routes, or carrier capabilities that are not implied by the input. "
                    "Keep output compact. Limit agent_reasoning to one short sentence per carrier. "
                    "Output ONLY the JSON object — no markdown, no explanations before or after."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Order: {order_context}\n\nCarriers to evaluate:\n{carrier_list}"
                ),
            },
        ],
        profile="reasoning_json",
    )

    return _validate_carrier_evaluation(result.content)


REJECTION_PRECEDENCE: dict[CarrierRejectionReason, int] = {
    CarrierRejectionReason.INVALID_DOCUMENTATION: 0,
    CarrierRejectionReason.ADR_NOT_SUPPORTED: 1,
    CarrierRejectionReason.TRUCK_TYPE_MISMATCH: 2,
    CarrierRejectionReason.NON_PROFITABLE: 3,
}

_MAX_SNAPSHOT_CANDIDATES = 8
_MIN_SNAPSHOT_CANDIDATES = 3

# Scoring weights
_ROUTE_MATCH_WEIGHT = Decimal("0.35")
_PRICE_COMPETITIVENESS_WEIGHT = Decimal("0.30")
_RELIABILITY_WEIGHT = Decimal("0.20")
_TRUCK_ADR_WEIGHT = Decimal("0.15")


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal_or_zero(value: Decimal | None) -> Decimal:
    return value or Decimal("0.00")


def _parse_country(text: str | None) -> str | None:
    """Extract country code from 'City, CC' format."""
    if text is None:
        return None
    parts = text.split(",")
    if len(parts) >= 2:
        return parts[-1].strip().upper()
    return None


def _compute_route_match_score(
    order: LoadOrder,
    carrier: CanonicalCarrier,
) -> tuple[Decimal, str]:
    """Score route compatibility. Returns (score 0-100, reasoning)."""
    origin_country = _parse_country(order.origin_text)
    destination_country = _parse_country(order.destination_text)

    if origin_country is None or destination_country is None:
        return Decimal("50.0"), "Route data incomplete — moderate fit assumed"

    countries = set(carrier.service_countries or [])
    lanes = set(carrier.preferred_lanes or [])
    route_pair = f"{origin_country}->{destination_country}"

    origin_covered = origin_country in countries
    dest_covered = destination_country in countries
    lane_match = route_pair in lanes

    if lane_match:
        return Decimal("100.0"), f"Strong lane match for {route_pair}"
    if origin_covered and dest_covered:
        return Decimal("80.0"), f"Both {origin_country} and {destination_country} in service area"
    if origin_covered or dest_covered:
        return Decimal("40.0"), f"Partial coverage — only {'origin' if origin_covered else 'destination'} in service area"
    return Decimal("10.0"), f"Route {route_pair} outside typical service area"


def _compute_price_competitiveness(
    carrier_price: Decimal,
    all_candidate_prices: list[Decimal],
) -> tuple[Decimal, str]:
    """Score price competitiveness relative to other candidates. Returns (score 0-100, reasoning)."""
    if not all_candidate_prices or carrier_price is None:
        return Decimal("50.0"), "No price comparison available"

    valid_prices = [p for p in all_candidate_prices if p > 0]
    if not valid_prices:
        return Decimal("50.0"), "No valid prices for comparison"

    min_price = min(valid_prices)
    max_price = max(valid_prices)

    if max_price == min_price:
        return Decimal("75.0"), "Competitive pricing — all carriers priced similarly"

    # Lower price = higher score
    normalized = (max_price - carrier_price) / (max_price - min_price)
    score = Decimal(str(float(normalized) * 100)).quantize(Decimal("0.1"))

    if score >= 80:
        return score, "Highly competitive pricing"
    elif score >= 50:
        return score, "Moderately competitive pricing"
    else:
        return score, "Higher-priced option"


def _compute_reliability_score(carrier: CanonicalCarrier) -> tuple[Decimal, str]:
    """Score based on reliability rating. Returns (score 0-100, reasoning)."""
    rating = carrier.reliability_rating or Decimal("5.0")
    # Scale from 0-10 to 0-100
    score = (rating * 10).quantize(Decimal("0.1"))
    if score >= 90:
        return score, "Excellent reliability track record"
    elif score >= 75:
        return score, "Good reliability rating"
    else:
        return score, "Below-average reliability"


def _compute_truck_adr_score(
    order: LoadOrder,
    carrier: CanonicalCarrier,
) -> tuple[Decimal, str]:
    """Score truck type and ADR compatibility. Returns (score 0-100, reasoning)."""
    score = Decimal("100.0")
    reasons = []

    if order.adr_required and not carrier.adr_capable:
        return Decimal("0.0"), "ADR required but carrier lacks ADR certification"

    if order.adr_required and carrier.adr_capable:
        reasons.append("ADR compatible")

    if (
        order.truck_type_id is not None
        and carrier.truck_type_id is not None
        and order.truck_type_id != carrier.truck_type_id
    ):
        return Decimal("0.0"), "Truck type mismatch"

    if not reasons:
        return Decimal("80.0"), "Standard compatibility"

    return score, ", ".join(reasons)


def _compute_carrier_price(
    order: LoadOrder,
    carrier: CanonicalCarrier,
) -> Decimal:
    """Compute carrier price based on pricing model."""
    distance = _decimal_or_zero(order.distance_km)

    if carrier.pricing_model == CarrierPricingModel.FLAT_RATE:
        base = _decimal_or_zero(carrier.flat_rate_amount)
    elif carrier.pricing_model == CarrierPricingModel.MARKET_ADJUSTED:
        base = distance * _decimal_or_zero(carrier.base_price_km)
        fuel_pct = _decimal_or_zero(carrier.fuel_surcharge_pct)
        base = base * (1 + fuel_pct / 100)
    else:  # PER_KM
        base = distance * _decimal_or_zero(carrier.base_price_km)

    return _money(base)


def _build_reasoning(
    route_score: Decimal,
    price_score: Decimal,
    reliability_score: Decimal,
    truck_adr_score: Decimal,
    rejection_reason: CarrierRejectionReason | None,
    route_reasoning: str,
    price_reasoning: str,
    reliability_reasoning: str,
    truck_adr_reasoning: str,
) -> str:
    """Build human-readable agent reasoning."""
    if rejection_reason is not None:
        return f"Rejected: {rejection_reason.value.replace('_', ' ')}. {truck_adr_reasoning if rejection_reason in (CarrierRejectionReason.ADR_NOT_SUPPORTED, CarrierRejectionReason.TRUCK_TYPE_MISMATCH) else route_reasoning}"

    parts = []
    if route_score >= 80:
        parts.append(route_reasoning)
    if price_score >= 70:
        parts.append(price_reasoning)
    if reliability_score >= 85:
        parts.append(reliability_reasoning)

    if not parts:
        parts.append(route_reasoning)
        parts.append(price_reasoning)

    return ". ".join(parts) + "."


@dataclass(frozen=True)
class ScoredCandidate:
    carrier: CanonicalCarrier
    proposal_status: TripProposalStatus
    rejection_reason: CarrierRejectionReason | None
    carrier_price: Decimal
    profit_margin: Decimal
    ranking_score: Decimal
    score_breakdown: dict[str, object]
    agent_reasoning: str


def _annotate_candidate_reasoning(
    candidates: list[ScoredCandidate],
    prefix: str,
) -> list[ScoredCandidate]:
    annotated: list[ScoredCandidate] = []
    for candidate in candidates:
        reasoning = candidate.agent_reasoning or ""
        annotated.append(
            replace(
                candidate,
                agent_reasoning=f"{prefix} {reasoning}".strip(),
            )
        )
    return annotated


def _evaluate_carriers(
    order: LoadOrder,
    carriers: list[CanonicalCarrier],
) -> list[ScoredCandidate]:
    """Evaluate and score all carriers against an order."""
    # First pass: compute prices and hard rejections
    preliminary: list[tuple[CanonicalCarrier, Decimal, Decimal, CarrierRejectionReason | None, str]] = []
    for carrier in carriers:
        carrier_price = _compute_carrier_price(order, carrier)
        profit_margin = _money(_decimal_or_zero(order.customer_price) - carrier_price)

        rejection_reason: CarrierRejectionReason | None = None
        if not carrier.documentation_valid:
            rejection_reason = CarrierRejectionReason.INVALID_DOCUMENTATION
        elif order.adr_required and not carrier.adr_capable:
            rejection_reason = CarrierRejectionReason.ADR_NOT_SUPPORTED
        elif (
            order.truck_type_id is not None
            and carrier.truck_type_id is not None
            and order.truck_type_id != carrier.truck_type_id
        ):
            rejection_reason = CarrierRejectionReason.TRUCK_TYPE_MISMATCH
        elif profit_margin <= 0:
            rejection_reason = CarrierRejectionReason.NON_PROFITABLE

        preliminary.append((carrier, carrier_price, profit_margin, rejection_reason, ""))

    # Collect candidate prices for competitiveness scoring
    candidate_prices = [
        cp for _, cp, pm, rr, _ in preliminary
        if rr is None and cp > 0
    ]

    # Second pass: compute full scores
    results: list[ScoredCandidate] = []
    for carrier, carrier_price, profit_margin, rejection_reason, _ in preliminary:
        route_score, route_reasoning = _compute_route_match_score(order, carrier)
        price_score, price_reasoning = _compute_price_competitiveness(carrier_price, candidate_prices)
        reliability_score, reliability_reasoning = _compute_reliability_score(carrier)
        truck_adr_score, truck_adr_reasoning = _compute_truck_adr_score(order, carrier)

        if rejection_reason is not None:
            overall = Decimal("0.0")
            proposal_status = TripProposalStatus.REJECTED
        else:
            overall = (
                route_score * _ROUTE_MATCH_WEIGHT
                + price_score * _PRICE_COMPETITIVENESS_WEIGHT
                + reliability_score * _RELIABILITY_WEIGHT
                + truck_adr_score * _TRUCK_ADR_WEIGHT
            ).quantize(Decimal("0.1"))
            proposal_status = TripProposalStatus.CANDIDATE

        reasoning = _build_reasoning(
            route_score, price_score, reliability_score, truck_adr_score,
            rejection_reason, route_reasoning, price_reasoning,
            reliability_reasoning, truck_adr_reasoning,
        )

        results.append(ScoredCandidate(
            carrier=carrier,
            proposal_status=proposal_status,
            rejection_reason=rejection_reason,
            carrier_price=carrier_price,
            profit_margin=profit_margin,
            ranking_score=overall,
            score_breakdown={
                "route_match": float(route_score),
                "price_competitiveness": float(price_score),
                "reliability": float(reliability_score),
                "truck_adr_compatibility": float(truck_adr_score),
                "overall": float(overall),
            },
            agent_reasoning=reasoning,
        ))

    return results


async def get_carrier_search_order_or_404(session: AsyncSession, load_order_id: UUID) -> LoadOrder:
    load_order = await session.get(LoadOrder, load_order_id)
    if load_order is None:
        raise HTTPException(status_code=404, detail="Load order not found")
    return load_order


async def get_locked_carrier_search_order_or_404(
    session: AsyncSession,
    load_order_id: UUID,
) -> LoadOrder:
    result = await session.execute(
        select(LoadOrder)
        .where(LoadOrder.id == load_order_id)
        .with_for_update()
    )
    load_order = result.scalar_one_or_none()
    if load_order is None:
        raise HTTPException(status_code=404, detail="Load order not found")
    return load_order


def _validate_search_prerequisites(load_order: LoadOrder) -> None:
    if load_order.customer_price is None:
        raise HTTPException(status_code=422, detail="Carrier search requires customer_price")
    if load_order.distance_km is None:
        raise HTTPException(status_code=422, detail="Carrier search requires distance_km")


async def list_load_order_trips(session: AsyncSession, load_order_id: UUID) -> list[Trip]:
    result = await session.execute(
        select(Trip)
        .options(selectinload(Trip.carrier))
        .where(Trip.load_order_id == load_order_id)
    )
    return list(result.scalars().all())


async def ensure_canonical_carrier_catalog(session: AsyncSession) -> None:
    """Ensure the expanded carrier catalog is persisted."""
    await ensure_canonical_prototype_truck_types(session)

    existing_ids = {c.id for c in CANONICAL_CARRIERS}
    result = await session.execute(
        select(Carrier).where(Carrier.id.in_(existing_ids))
    )
    existing_map = {carrier.id: carrier for carrier in result.scalars().all()}

    for canonical in CANONICAL_CARRIERS:
        existing = existing_map.get(canonical.id)
        if existing is None:
            session.add(Carrier(
                id=canonical.id,
                company_name=canonical.company_name,
                truck_type_id=canonical.truck_type_id,
                reliability_rating=canonical.reliability_rating,
                documentation_valid=canonical.documentation_valid,
                adr_capable=canonical.adr_capable,
                base_price_km=canonical.base_price_km,
                home_base_text=canonical.home_base_text,
                service_countries=canonical.service_countries,
                preferred_lanes=canonical.preferred_lanes,
                pricing_model=canonical.pricing_model,
                flat_rate_amount=canonical.flat_rate_amount,
                fuel_surcharge_pct=canonical.fuel_surcharge_pct,
            ))
            continue

        existing.company_name = canonical.company_name
        existing.truck_type_id = canonical.truck_type_id
        existing.reliability_rating = canonical.reliability_rating
        existing.documentation_valid = canonical.documentation_valid
        existing.adr_capable = canonical.adr_capable
        existing.base_price_km = canonical.base_price_km
        existing.home_base_text = canonical.home_base_text
        existing.service_countries = canonical.service_countries
        existing.preferred_lanes = canonical.preferred_lanes
        existing.pricing_model = canonical.pricing_model
        existing.flat_rate_amount = canonical.flat_rate_amount
        existing.fuel_surcharge_pct = canonical.fuel_surcharge_pct

    await session.flush()


async def _list_catalog_carriers(session: AsyncSession) -> list[CanonicalCarrier]:
    """List carriers from the catalog, returning canonical definitions."""
    return list(CANONICAL_CARRIERS)


def _to_candidate_response(
    trip: Trip,
    *,
    selected_trip_id: UUID | None,
) -> CarrierCandidateResponse:
    assert trip.carrier is not None
    canonical = None
    for c in CANONICAL_CARRIERS:
        if c.id == trip.carrier.id:
            canonical = c
            break

    return CarrierCandidateResponse(
        trip_id=trip.id,
        carrier_id=trip.carrier.id,
        company_name=canonical.company_name if canonical is not None else trip.carrier.company_name,
        truck_type_id=canonical.truck_type_id if canonical is not None else trip.carrier.truck_type_id,
        reliability_rating=canonical.reliability_rating if canonical is not None else trip.carrier.reliability_rating,
        documentation_valid=canonical.documentation_valid if canonical is not None else trip.carrier.documentation_valid,
        adr_capable=canonical.adr_capable if canonical is not None else trip.carrier.adr_capable,
        base_price_km=canonical.base_price_km if canonical is not None else trip.carrier.base_price_km,
        carrier_price=trip.carrier_price,
        profit_margin=trip.profit_margin,
        proposal_status=TripProposalStatus(trip.proposal_status),
        ai_rejection_reason=(
            CarrierRejectionReason(trip.ai_rejection_reason)
            if trip.ai_rejection_reason is not None
            else None
        ),
        is_selected=trip.id == selected_trip_id,
        ranking_score=trip.ranking_score,
        score_breakdown=trip.score_breakdown,
        agent_reasoning=trip.agent_reasoning,
    )


def _candidate_sort_key(candidate: CarrierCandidateResponse) -> tuple[object, ...]:
    if candidate.proposal_status == TripProposalStatus.CANDIDATE:
        return (
            0,
            -_decimal_or_zero(candidate.ranking_score),
            -_decimal_or_zero(candidate.profit_margin),
            candidate.company_name,
        )

    assert candidate.ai_rejection_reason is not None
    return (
        1,
        REJECTION_PRECEDENCE[candidate.ai_rejection_reason],
        -_decimal_or_zero(candidate.reliability_rating),
        candidate.company_name,
    )


def _scored_candidate_sort_key(candidate: ScoredCandidate) -> tuple[object, ...]:
    if candidate.proposal_status == TripProposalStatus.CANDIDATE:
        return (
            0,
            -candidate.ranking_score,
            -candidate.profit_margin,
            candidate.carrier.company_name,
        )

    assert candidate.rejection_reason is not None
    return (
        1,
        REJECTION_PRECEDENCE[candidate.rejection_reason],
        -(candidate.carrier.reliability_rating or Decimal("0.00")),
        candidate.carrier.company_name,
    )


def _shortlist_scored_candidates(scored: list[ScoredCandidate]) -> list[ScoredCandidate]:
    ordered = sorted(scored, key=_scored_candidate_sort_key)
    shortlist = ordered[:_MAX_SNAPSHOT_CANDIDATES]

    candidate_count = sum(
        1 for item in shortlist if item.proposal_status == TripProposalStatus.CANDIDATE
    )
    if candidate_count >= _MIN_SNAPSHOT_CANDIDATES:
        return shortlist

    seen_ids = {item.carrier.id for item in shortlist}
    for item in ordered[_MAX_SNAPSHOT_CANDIDATES:]:
        if item.carrier.id in seen_ids:
            continue
        shortlist.append(item)
        seen_ids.add(item.carrier.id)
        if item.proposal_status == TripProposalStatus.CANDIDATE:
            candidate_count += 1
        if candidate_count >= _MIN_SNAPSHOT_CANDIDATES:
            break

    return shortlist[:_MAX_SNAPSHOT_CANDIDATES]


def build_carrier_search_response(
    load_order: LoadOrder,
    trips: list[Trip],
) -> CarrierSearchResponse:
    effective_status, effective_selected_trip_id = _derive_effective_snapshot_state(
        load_order,
        trips,
    )
    candidates = sorted(
        (
            _to_candidate_response(
                trip,
                selected_trip_id=effective_selected_trip_id,
            )
            for trip in trips
        ),
        key=_candidate_sort_key,
    )
    return CarrierSearchResponse(
        load_order=LoadOrderResponse.model_validate(load_order).model_copy(
            update={
                "status": effective_status,
                "selected_trip_id": effective_selected_trip_id,
            }
        ),
        candidates=candidates,
    )


def _has_valid_selected_trip(load_order: LoadOrder, trips: list[Trip]) -> bool:
    if load_order.selected_trip_id is None:
        return False

    selected_trip = next((trip for trip in trips if trip.id == load_order.selected_trip_id), None)
    if selected_trip is None:
        return False

    return TripProposalStatus(selected_trip.proposal_status) == TripProposalStatus.CANDIDATE


def _derive_effective_snapshot_state(
    load_order: LoadOrder,
    trips: list[Trip],
) -> tuple[LoadOrderStatus, UUID | None]:
    if load_order.status not in {
        LoadOrderStatus.SEARCHING_CARRIER,
        LoadOrderStatus.READY_FOR_FORMALIZATION,
        LoadOrderStatus.FORMALIZED,
        LoadOrderStatus.VIABILITY_CONFIRMED,
    }:
        return load_order.status, load_order.selected_trip_id

    if _has_valid_selected_trip(load_order, trips):
        if load_order.status == LoadOrderStatus.FORMALIZED:
            return LoadOrderStatus.FORMALIZED, load_order.selected_trip_id
        return LoadOrderStatus.READY_FOR_FORMALIZATION, load_order.selected_trip_id

    return LoadOrderStatus.SEARCHING_CARRIER, None


def _normalize_reused_snapshot_state(load_order: LoadOrder, trips: list[Trip]) -> bool:
    original_status = load_order.status
    original_selected_trip_id = load_order.selected_trip_id
    normalized_status, normalized_selected_trip_id = _derive_effective_snapshot_state(
        load_order,
        trips,
    )
    state_changed = (
        original_status != normalized_status
        or original_selected_trip_id != normalized_selected_trip_id
    )
    load_order.selected_trip_id = normalized_selected_trip_id
    load_order.status = normalized_status
    return state_changed


async def _evaluate_orchestrated(
    order: LoadOrder,
    carriers: list[CanonicalCarrier],
    session: AsyncSession | None = None,
) -> list[ScoredCandidate]:
    from app.backend.core.settings import get_settings

    settings = get_settings()
    heuristic_scored = _evaluate_carriers(order, carriers)
    shortlist = _shortlist_scored_candidates(heuristic_scored)
    shortlist_carriers = [candidate.carrier for candidate in shortlist]

    if settings.reasoning_model_name:
        try:
            return await _evaluate_carriers_cloud(order, shortlist_carriers, settings, session)
        except Exception as exc:
            logger.warning("Cloud reasoning failed for order %s: %s", order.id, exc)
            fallback_msg = f"Fallback heuristic evaluation: cloud reasoning failed — {exc}"
            return _annotate_candidate_reasoning(shortlist, fallback_msg)

    return shortlist


def _canonical_slug(name: str) -> str:
    return name.lower().replace(" ", "-")


async def _evaluate_carriers_cloud(
    order: LoadOrder,
    carriers: list[CanonicalCarrier],
    settings: Settings,
    session: AsyncSession | None = None,
) -> list[ScoredCandidate]:
    origin = order.origin_text or "unknown"
    dest = order.destination_text or "unknown"
    adr = "required" if order.adr_required else "not required"
    truck = str(order.truck_type_id) if order.truck_type_id else "any"

    order_context = (
        f"Route: {origin} -> {dest}, ADR: {adr}, Truck type: {truck}, "
        f"Customer price: {order.customer_price} {order.currency}, "
        f"Distance: {order.distance_km} km"
    )

    retrieval_context = ""
    if session is not None:
        try:
            from app.backend.services.runtime_settings import load_boolean_settings
            bool_settings = await load_boolean_settings(session)
            if bool_settings.get("enable_carrier_search_retrieval"):
                from app.backend.services.rag_memory import retrieve_carrier_search_context
                query = f"{origin} {dest} {adr} {truck}"
                snippets = retrieve_carrier_search_context(query, top_k=3)
                if snippets:
                    retrieval_context = "\n\nSimilar past orders:\n"
                    for s in snippets:
                        retrieval_context += f"- {s['document']}\n"
        except Exception:
            pass

    full_context = order_context + retrieval_context

    carrier_names = [c.company_name for c in carriers]
    evaluation = await _evaluate_carriers_with_reasoning(
        settings=settings,
        order_context=full_context,
        carrier_names=carrier_names,
    )

    if not evaluation.candidates:
        return _evaluate_carriers(order, carriers)

    name_map: dict[str, CanonicalCarrier] = {
        _canonical_slug(c.company_name): c for c in carriers
    }

    results: list[ScoredCandidate] = []
    for ev in evaluation.candidates:
        canonical = name_map.get(ev.carrier_id) or name_map.get(_canonical_slug(ev.carrier_id))
        if canonical is None:
            continue

        carrier_price = _compute_carrier_price(order, canonical)
        profit_margin = _money(_decimal_or_zero(order.customer_price) - carrier_price)

        ps = TripProposalStatus.CANDIDATE
        rr: CarrierRejectionReason | None = None
        if ev.proposal_status == "rejected":
            ps = TripProposalStatus.REJECTED
            try:
                rr = CarrierRejectionReason(ev.rejection_reason or "")
            except ValueError:
                rr = CarrierRejectionReason.NON_PROFITABLE

        results.append(ScoredCandidate(
            carrier=canonical,
            proposal_status=ps,
            rejection_reason=rr,
            carrier_price=carrier_price,
            profit_margin=profit_margin,
            ranking_score=Decimal(str(ev.ranking_score)).quantize(Decimal("0.1")),
            score_breakdown={k: float(v) for k, v in ev.score_breakdown.items()},
            agent_reasoning=ev.agent_reasoning,
        ))

    if len(results) < len(carriers):
        raise RuntimeError("Cloud reasoning returned incomplete carrier coverage")

    return _annotate_candidate_reasoning(results, "Cloud reasoning:")


async def create_load_order_carrier_search(
    session: AsyncSession,
    load_order_id: UUID,
) -> tuple[CarrierSearchResponse, bool]:
    load_order = await get_locked_carrier_search_order_or_404(session, load_order_id)
    await ensure_canonical_carrier_catalog(session)
    existing_trips = await list_load_order_trips(session, load_order_id)

    if existing_trips:
        if load_order.status not in {
            LoadOrderStatus.VIABILITY_CONFIRMED,
            LoadOrderStatus.SEARCHING_CARRIER,
            LoadOrderStatus.READY_FOR_FORMALIZATION,
            LoadOrderStatus.FORMALIZED,
        }:
            raise HTTPException(
                status_code=409,
                detail=f"Carrier search not allowed for status: {load_order.status}",
            )

        if _normalize_reused_snapshot_state(load_order, existing_trips):
            await session.flush()

        return build_carrier_search_response(load_order, existing_trips), False

    if load_order.status != LoadOrderStatus.VIABILITY_CONFIRMED:
        raise HTTPException(
            status_code=409,
            detail=f"Carrier search not allowed for status: {load_order.status}",
        )

    _validate_search_prerequisites(load_order)
    carriers = await _list_catalog_carriers(session)

    scored = await _evaluate_orchestrated(load_order, carriers, session)

    for candidate in scored:
        session.add(Trip(
            load_order_id=load_order.id,
            carrier_id=candidate.carrier.id,
            carrier_price=candidate.carrier_price,
            profit_margin=candidate.profit_margin,
            proposal_status=candidate.proposal_status.value,
            ai_rejection_reason=(
                candidate.rejection_reason.value
                if candidate.rejection_reason is not None
                else None
            ),
            ranking_score=candidate.ranking_score,
            score_breakdown=candidate.score_breakdown,
            agent_reasoning=candidate.agent_reasoning,
        ))

    validate_load_order_transition(load_order.status, LoadOrderStatus.SEARCHING_CARRIER)
    load_order.status = LoadOrderStatus.SEARCHING_CARRIER
    await session.flush()

    trips = await list_load_order_trips(session, load_order_id)
    return build_carrier_search_response(load_order, trips), True


async def get_load_order_carrier_candidates(
    session: AsyncSession,
    load_order_id: UUID,
) -> CarrierSearchResponse:
    load_order = await get_carrier_search_order_or_404(session, load_order_id)
    trips = await list_load_order_trips(session, load_order_id)
    if not trips:
        raise HTTPException(status_code=404, detail="Load order has no carrier-search snapshot")

    return build_carrier_search_response(load_order, trips)
