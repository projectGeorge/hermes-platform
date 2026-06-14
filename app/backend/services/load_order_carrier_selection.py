"""Services for explicit carrier proposal selection."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.domain_enums import (
    LoadOrderStatus,
    TripProposalStatus,
    validate_load_order_transition,
)
from app.backend.schemas.carrier_search import CarrierSearchResponse
from app.backend.services.load_order_carrier_search import (
    build_carrier_search_response,
    get_locked_carrier_search_order_or_404,
    list_load_order_trips,
)


SELECTABLE_CARRIER_SELECTION_STATUSES = {
    LoadOrderStatus.SEARCHING_CARRIER,
    LoadOrderStatus.READY_FOR_FORMALIZATION,
    LoadOrderStatus.FORMALIZED,
}


async def select_load_order_carrier(
    session: AsyncSession,
    load_order_id: UUID,
    trip_id: UUID | None,
) -> CarrierSearchResponse:
    load_order = await get_locked_carrier_search_order_or_404(session, load_order_id)
    trips = await list_load_order_trips(session, load_order_id)

    if not trips:
        raise HTTPException(status_code=404, detail="Load order has no carrier-search snapshot")

    if load_order.status not in SELECTABLE_CARRIER_SELECTION_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Carrier selection not allowed for status: {load_order.status}",
        )

    if trip_id is None:
        load_order.selected_trip_id = None
        if load_order.status in {
            LoadOrderStatus.READY_FOR_FORMALIZATION,
            LoadOrderStatus.FORMALIZED,
        }:
            load_order.status = LoadOrderStatus.SEARCHING_CARRIER
        await session.flush()
        return build_carrier_search_response(load_order, trips)

    selected_trip = next((trip for trip in trips if trip.id == trip_id), None)
    if selected_trip is None:
        raise HTTPException(status_code=404, detail="Trip not found for load order")

    if TripProposalStatus(selected_trip.proposal_status) != TripProposalStatus.CANDIDATE:
        raise HTTPException(status_code=409, detail="Carrier selection requires a candidate trip")

    if load_order.status == LoadOrderStatus.SEARCHING_CARRIER:
        validate_load_order_transition(
            load_order.status,
            LoadOrderStatus.READY_FOR_FORMALIZATION,
        )
        load_order.status = LoadOrderStatus.READY_FOR_FORMALIZATION

    load_order.selected_trip_id = selected_trip.id
    await session.flush()

    return build_carrier_search_response(load_order, trips)
