"""Services for Human-in-the-Loop load-order review and confirmation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.domain_enums import (
    LoadOrderHumanReviewStatus,
    LoadOrderStatus,
    IngestionRunStatus,
    validate_load_order_transition,
)
from app.backend.models.ingestion_run import IngestionRun
from app.backend.models.load_order import LoadOrder
from app.backend.models.load_order_human_review import LoadOrderHumanReview
from app.backend.models.user import User
from app.backend.schemas.human_validation import (
    HumanValidationConfirmRequest,
    HumanValidationContextResponse,
    HumanValidationLatestIngestionRunResponse,
    HumanValidationUpdateRequest,
)
from app.backend.schemas.load_order import LoadOrderResponse, LoadOrderUpdate
from app.backend.services.load_orders import validate_load_order_payload
from app.backend.services.prototype_catalog import ensure_canonical_prototype_truck_types

_TRACKED_FIELDS: tuple[str, ...] = (
    "customer_name",
    "origin_text",
    "destination_text",
    "origin_load_date",
    "cargo_description",
    "weight_kg",
    "customer_price",
)

_MINIMUM_REQUIRED_FIELDS: tuple[str, ...] = (
    "customer_name",
    "origin_text",
    "destination_text",
    "origin_load_date",
    "cargo_description",
)

_REVIEWABLE_FIELDS: tuple[str, ...] = (
    "customer_name",
    "origin_text",
    "destination_text",
    "origin_load_date",
    "destination_unload_date",
    "distance_km",
    "cargo_description",
    "weight_kg",
    "truck_type_id",
    "customer_price",
    "currency",
    "adr_required",
)

async def _get_load_order_or_404(
    session: AsyncSession,
    load_order_id: UUID,
) -> LoadOrder:
    load_order = await session.get(LoadOrder, load_order_id)
    if load_order is None:
        raise HTTPException(status_code=404, detail="Load order not found")

    return load_order


async def _get_reviewer_or_404(
    session: AsyncSession,
    reviewed_by_user_id: UUID,
) -> User:
    reviewer = await session.get(User, reviewed_by_user_id)
    if reviewer is None:
        raise HTTPException(status_code=404, detail="Reviewer user not found")

    return reviewer


async def _get_latest_ingestion_run_or_404(
    session: AsyncSession,
    load_order_id: UUID,
) -> IngestionRun:
    result = await session.execute(
        select(IngestionRun)
        .where(IngestionRun.load_order_id == load_order_id)
        .order_by(IngestionRun.created_at.desc(), IngestionRun.id.desc())
        .limit(1)
    )
    ingestion_run = result.scalar_one_or_none()
    if ingestion_run is None:
        load_order = await _get_load_order_or_404(session, load_order_id)
        ingestion_run = await _create_manual_review_ingestion_run(session, load_order)

    return ingestion_run


def _build_manual_review_raw_text(load_order: LoadOrder) -> str:
    lines = [
        f"Customer: {load_order.customer_name or 'TBD'}",
        f"Origin: {load_order.origin_text or 'TBD'}",
        f"Destination: {load_order.destination_text or 'TBD'}",
        f"Load Date: {load_order.origin_load_date.isoformat() if load_order.origin_load_date else 'TBD'}",
        f"Cargo: {load_order.cargo_description or 'TBD'}",
    ]
    if load_order.distance_km is not None:
        lines.append(f"Distance: {load_order.distance_km} km")
    if load_order.weight_kg is not None:
        lines.append(f"Weight: {load_order.weight_kg}")
    if load_order.customer_price is not None:
        lines.append(f"Price: {load_order.customer_price}")
    if load_order.truck_type_id is not None:
        lines.append(f"Truck Type ID: {load_order.truck_type_id}")
    lines.append(f"Currency: {load_order.currency}")
    lines.append(f"ADR: {'yes' if load_order.adr_required else 'no'}")
    return "\n".join(lines)


def _build_manual_extracted_payload(load_order: LoadOrder) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "currency": load_order.currency,
        "adr_required": load_order.adr_required,
    }
    for field_name in _TRACKED_FIELDS:
        value = getattr(load_order, field_name)
        if value not in (None, ""):
            payload[field_name] = value
    if load_order.destination_unload_date is not None:
        payload["destination_unload_date"] = load_order.destination_unload_date
    if load_order.truck_type_id is not None:
        payload["truck_type_id"] = load_order.truck_type_id
    return jsonable_encoder(payload)


async def _create_manual_review_ingestion_run(
    session: AsyncSession,
    load_order: LoadOrder,
) -> IngestionRun:
    missing_fields = _build_missing_fields(_build_manual_extracted_payload(load_order))
    ingestion_run = IngestionRun(
        user_id=load_order.user_id,
        route="manual_order_review",
        status=IngestionRunStatus.COMPLETED,
        raw_text=_build_manual_review_raw_text(load_order),
        extracted_payload=_build_manual_extracted_payload(load_order),
        missing_fields=missing_fields or None,
        load_order_id=load_order.id,
        execution_path="manual",
        provider="operator",
        model_name="manual-order-entry",
        trace_steps=[{"node": "manual_context", "outcome": "synthesized"}],
    )
    session.add(ingestion_run)
    await session.flush()
    return ingestion_run


def _build_effective_fields(
    load_order: LoadOrder,
    ingestion_run: IngestionRun,
) -> dict[str, Any]:
    return {
        "customer_name": load_order.customer_name,
        "origin_text": load_order.origin_text,
        "destination_text": load_order.destination_text,
        "origin_load_date": load_order.origin_load_date,
        "destination_unload_date": load_order.destination_unload_date,
        "distance_km": load_order.distance_km,
        "cargo_description": load_order.cargo_description,
        "weight_kg": load_order.weight_kg,
        "truck_type_id": load_order.truck_type_id,
        "customer_price": load_order.customer_price,
        "currency": load_order.currency,
        "adr_required": load_order.adr_required,
    }


def _build_missing_fields(effective_fields: dict[str, Any]) -> dict[str, str]:
    return {
        field_name: "not_found"
        for field_name in _TRACKED_FIELDS
        if effective_fields.get(field_name) in (None, "")
    }


def _has_viability_minimum(missing_fields: dict[str, str]) -> bool:
    return not any(field_name in missing_fields for field_name in _MINIMUM_REQUIRED_FIELDS)


def _build_load_order_response(
    load_order: LoadOrder,
    missing_fields: dict[str, str],
) -> LoadOrderResponse:
    response = LoadOrderResponse.model_validate(load_order)
    return response.model_copy(update={"missing_fields": missing_fields or None})


def _build_context_response(
    load_order: LoadOrder,
    ingestion_run: IngestionRun,
    missing_fields: dict[str, str],
) -> HumanValidationContextResponse:
    return HumanValidationContextResponse(
        load_order=_build_load_order_response(load_order, missing_fields),
        latest_ingestion_run=HumanValidationLatestIngestionRunResponse.model_validate(
            ingestion_run
        ),
        missing_fields=missing_fields,
        blocked_missing_fields={},
        reviewable_fields=list(_REVIEWABLE_FIELDS),
        can_confirm_viability=(
            load_order.status == LoadOrderStatus.VIABILITY_PENDING
            and not missing_fields
        ),
    )


def _review_update_fields(payload: HumanValidationUpdateRequest) -> dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    return {
        field_name: update_data[field_name]
        for field_name in _REVIEWABLE_FIELDS
        if field_name in update_data
    }


def _validate_effective_schedule(
    load_order: LoadOrder,
    update_fields: dict[str, Any],
) -> None:
    payload = LoadOrderUpdate(
        origin_load_date=update_fields.get("origin_load_date", load_order.origin_load_date),
        destination_unload_date=update_fields.get(
            "destination_unload_date",
            load_order.destination_unload_date,
        ),
    )
    try:
        validate_load_order_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _ensure_truck_type_seeded_if_needed(
    session: AsyncSession,
    update_fields: dict[str, Any],
) -> None:
    if update_fields.get("truck_type_id") is not None:
        await ensure_canonical_prototype_truck_types(session)


def _apply_review_fields(load_order: LoadOrder, update_fields: dict[str, Any]) -> None:
    for field_name, value in update_fields.items():
        setattr(load_order, field_name, value)


def _candidate_missing_fields(
    load_order: LoadOrder,
    ingestion_run: IngestionRun,
    update_fields: dict[str, Any],
) -> dict[str, str]:
    candidate_order = LoadOrder()
    candidate_order.customer_name = update_fields.get(
        "customer_name",
        load_order.customer_name,
    )
    candidate_order.origin_text = update_fields.get(
        "origin_text",
        load_order.origin_text,
    )
    candidate_order.destination_text = update_fields.get(
        "destination_text",
        load_order.destination_text,
    )
    candidate_order.origin_load_date = update_fields.get(
        "origin_load_date",
        load_order.origin_load_date,
    )
    candidate_order.destination_unload_date = update_fields.get(
        "destination_unload_date",
        load_order.destination_unload_date,
    )
    candidate_order.distance_km = update_fields.get("distance_km", load_order.distance_km)
    candidate_order.cargo_description = update_fields.get(
        "cargo_description",
        load_order.cargo_description,
    )
    candidate_order.weight_kg = update_fields.get("weight_kg", load_order.weight_kg)
    candidate_order.truck_type_id = update_fields.get("truck_type_id", load_order.truck_type_id)
    candidate_order.customer_price = update_fields.get(
        "customer_price",
        load_order.customer_price,
    )
    candidate_order.currency = update_fields.get("currency", load_order.currency)
    candidate_order.adr_required = update_fields.get("adr_required", load_order.adr_required)

    return _build_missing_fields(_build_effective_fields(candidate_order, ingestion_run))


def _validate_supported_review_state(current_status: LoadOrderStatus) -> None:
    if current_status not in {
        LoadOrderStatus.PENDING_INGESTION,
        LoadOrderStatus.VIABILITY_PENDING,
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Human validation not allowed for status: {current_status}",
        )


def _ensure_update_contains_review_data(update_fields: dict[str, Any]) -> None:
    if not update_fields:
        raise HTTPException(status_code=422, detail="Human validation update requires review data")


async def get_load_order_human_validation_context(
    session: AsyncSession,
    load_order_id: UUID,
) -> HumanValidationContextResponse:
    """Return the current Human-in-the-Loop context for an ingested order."""

    load_order = await _get_load_order_or_404(session, load_order_id)
    ingestion_run = await _get_latest_ingestion_run_or_404(session, load_order_id)
    missing_fields = _build_missing_fields(_build_effective_fields(load_order, ingestion_run))

    return _build_context_response(load_order, ingestion_run, missing_fields)


async def update_load_order_human_validation(
    session: AsyncSession,
    load_order_id: UUID,
    payload: HumanValidationUpdateRequest,
) -> HumanValidationContextResponse:
    """Apply operator review changes and update the order review state."""

    load_order = await _get_load_order_or_404(session, load_order_id)
    _validate_supported_review_state(load_order.status)
    ingestion_run = await _get_latest_ingestion_run_or_404(session, load_order_id)
    await _get_reviewer_or_404(session, payload.reviewed_by_user_id)

    update_fields = _review_update_fields(payload)
    _ensure_update_contains_review_data(update_fields)
    _validate_effective_schedule(load_order, update_fields)
    await _ensure_truck_type_seeded_if_needed(session, update_fields)

    missing_fields = _candidate_missing_fields(load_order, ingestion_run, update_fields)
    has_viability_minimum = _has_viability_minimum(missing_fields)

    if load_order.status == LoadOrderStatus.VIABILITY_PENDING and not has_viability_minimum:
        raise HTTPException(
            status_code=409,
            detail="Human validation update would make the order non-reviewable",
        )

    _apply_review_fields(load_order, update_fields)
    if load_order.status == LoadOrderStatus.PENDING_INGESTION and has_viability_minimum:
        try:
            validate_load_order_transition(
                load_order.status,
                LoadOrderStatus.VIABILITY_PENDING,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        load_order.status = LoadOrderStatus.VIABILITY_PENDING

    load_order.missing_fields = missing_fields or None
    session.add(
        LoadOrderHumanReview(
            load_order_id=load_order.id,
            ingestion_run_id=ingestion_run.id,
            reviewed_by_user_id=payload.reviewed_by_user_id,
            review_status=LoadOrderHumanReviewStatus.FIELDS_UPDATED,
            submitted_fields=jsonable_encoder(update_fields),
            remaining_missing_fields=missing_fields,
            review_notes=payload.review_notes,
        )
    )
    await session.flush()

    return _build_context_response(load_order, ingestion_run, missing_fields)


async def confirm_load_order_viability(
    session: AsyncSession,
    load_order_id: UUID,
    payload: HumanValidationConfirmRequest,
) -> LoadOrderResponse:
    """Persist the operator viability confirmation for a reviewable order."""

    load_order = await _get_load_order_or_404(session, load_order_id)
    ingestion_run = await _get_latest_ingestion_run_or_404(session, load_order_id)
    await _get_reviewer_or_404(session, payload.reviewed_by_user_id)

    missing_fields = _build_missing_fields(_build_effective_fields(load_order, ingestion_run))
    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail="Cannot confirm viability while missing_fields remain",
        )

    if load_order.status == LoadOrderStatus.PENDING_INGESTION:
        try:
            validate_load_order_transition(
                load_order.status,
                LoadOrderStatus.VIABILITY_PENDING,
            )
            load_order.status = LoadOrderStatus.VIABILITY_PENDING
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        validate_load_order_transition(
            load_order.status,
            LoadOrderStatus.VIABILITY_CONFIRMED,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    load_order.status = LoadOrderStatus.VIABILITY_CONFIRMED
    load_order.missing_fields = None
    session.add(
        LoadOrderHumanReview(
            load_order_id=load_order.id,
            ingestion_run_id=ingestion_run.id,
            reviewed_by_user_id=payload.reviewed_by_user_id,
            review_status=LoadOrderHumanReviewStatus.VIABILITY_CONFIRMED,
            submitted_fields={},
            remaining_missing_fields={},
            review_notes=payload.review_notes,
        )
    )
    await session.flush()

    return LoadOrderResponse.model_validate(load_order)
