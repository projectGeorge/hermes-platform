from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.domain_enums import (
    LoadOrderStatus,
    TripProposalStatus,
    validate_load_order_transition,
)
from app.backend.models.load_order import LoadOrder
from app.backend.models.trip import Trip
from app.backend.models.ingestion_run import IngestionRun
from app.backend.models.load_order_human_review import LoadOrderHumanReview
from app.backend.models.agent_activity import AgentActivity
from app.backend.models.execution_monitoring_snapshot import ExecutionMonitoringSnapshot
from app.backend.models.monitoring_alert import MonitoringAlert
from app.backend.schemas.load_order import (
    DashboardLoadOrderItem,
    DashboardLoadOrderSummaryResponse,
    LoadOrderCreate,
    LoadOrderCreateRequest,
    LoadOrderListPageResponse,
    LoadOrderResponse,
    LoadOrderUpdate,
)
from app.backend.services.prototype_catalog import (
    ensure_canonical_prototype_truck_types,
    is_canonical_prototype_truck_type_id,
)

_DASHBOARD_ATTENTION_STATUSES: tuple[LoadOrderStatus, ...] = (
    LoadOrderStatus.PENDING_INGESTION,
    LoadOrderStatus.VIABILITY_PENDING,
    LoadOrderStatus.VIABILITY_CONFIRMED,
    LoadOrderStatus.SEARCHING_CARRIER,
    LoadOrderStatus.READY_FOR_FORMALIZATION,
)

_RUNTIME_ERROR_DETAILS_TO_ENGLISH: dict[str, str] = {
    "Orden no encontrada": "Load order not found",
    "Transicion no permitida: viabilidad_pendiente -> lista_para_formalizar": (
        "Transition not allowed: viability_pending -> ready_for_formalization"
    ),
    "Transicion no permitida: viabilidad_pendiente -> formalizada": (
        "Transition not allowed: viability_pending -> formalized"
    ),
    "Transicion no permitida: viabilidad_confirmada -> lista_para_formalizar": (
        "Transition not allowed: viability_confirmed -> ready_for_formalization"
    ),
    "Transicion no permitida: viabilidad_confirmada -> formalizada": (
        "Transition not allowed: viability_confirmed -> formalized"
    ),
    "Transicion no permitida: cancelada -> lista_para_formalizar": (
        "Transition not allowed: cancelled -> ready_for_formalization"
    ),
    "Transicion no permitida: cancelada -> formalizada": (
        "Transition not allowed: cancelled -> formalized"
    ),
    "Transicion no permitida: cancelada -> viabilidad_confirmada": (
        "Transition not allowed: cancelled -> viability_confirmed"
    ),
}

_MANUAL_CREATE_TRACKED_FIELDS: tuple[str, ...] = (
    "customer_name",
    "origin_text",
    "destination_text",
    "origin_load_date",
    "cargo_description",
    "weight_kg",
    "customer_price",
    "distance_km",
)

_MANUAL_CREATE_MINIMUM_REQUIRED_FIELDS: tuple[str, ...] = (
    "customer_name",
    "origin_text",
    "destination_text",
    "origin_load_date",
    "cargo_description",
)


def _to_load_order_response(runtime_order: LoadOrder) -> LoadOrderResponse:
    return LoadOrderResponse(
        id=runtime_order.id,
        user_id=runtime_order.user_id,
        customer_id=runtime_order.customer_id,
        customer_name=runtime_order.customer_name,
        status=LoadOrderStatus(runtime_order.status),
        selected_trip_id=runtime_order.selected_trip_id,
        origin_id=runtime_order.origin_id,
        origin_text=runtime_order.origin_text,
        origin_load_date=runtime_order.origin_load_date,
        destination_id=runtime_order.destination_id,
        destination_text=runtime_order.destination_text,
        destination_unload_date=runtime_order.destination_unload_date,
        distance_km=runtime_order.distance_km,
        cargo_description=runtime_order.cargo_description,
        weight_kg=runtime_order.weight_kg,
        truck_type_id=runtime_order.truck_type_id,
        adr_required=runtime_order.adr_required,
        missing_fields=runtime_order.missing_fields,
        customer_price=runtime_order.customer_price,
        currency=runtime_order.currency,
        created_at=runtime_order.created_at,
        updated_at=runtime_order.updated_at,
    )


def _translate_runtime_http_exception(exc: HTTPException) -> HTTPException:
    detail = exc.detail
    if isinstance(detail, str):
        detail = _RUNTIME_ERROR_DETAILS_TO_ENGLISH.get(detail, detail)

    return HTTPException(status_code=exc.status_code, detail=detail, headers=exc.headers)


def _is_missing_order_field_value(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def derive_manual_create_defaults(
    payload: LoadOrderCreateRequest,
) -> tuple[LoadOrderStatus, dict[str, str] | None]:
    payload_data = payload.model_dump()
    missing_fields = {
        field_name: "not_found"
        for field_name in _MANUAL_CREATE_TRACKED_FIELDS
        if _is_missing_order_field_value(payload_data.get(field_name))
    }
    minimum_missing_fields = any(
        field_name in missing_fields
        for field_name in _MANUAL_CREATE_MINIMUM_REQUIRED_FIELDS
    )
    if minimum_missing_fields:
        status = LoadOrderStatus.PENDING_INGESTION
    elif not missing_fields:
        status = LoadOrderStatus.VIABILITY_CONFIRMED
    else:
        status = LoadOrderStatus.VIABILITY_PENDING
    return status, missing_fields or None


def validate_load_order_payload(payload: LoadOrderCreate | LoadOrderUpdate) -> None:
    if (
        payload.origin_load_date is not None
        and payload.destination_unload_date is not None
        and payload.destination_unload_date < payload.origin_load_date
    ):
        raise ValueError(
            "destination_unload_date cannot be earlier than origin_load_date"
        )


def _translate_validation_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _to_dashboard_order_item(runtime_order: LoadOrder) -> DashboardLoadOrderItem:
    return DashboardLoadOrderItem(
        id=runtime_order.id,
        customer_name=runtime_order.customer_name,
        status=LoadOrderStatus(runtime_order.status),
        origin_text=runtime_order.origin_text,
        destination_text=runtime_order.destination_text,
        updated_at=runtime_order.updated_at,
    )


def _build_order_filters(
    *,
    status: LoadOrderStatus | None = None,
    user_id: UUID | None = None,
    customer_id: UUID | None = None,
    active_only: bool = False,
    search: str | None = None,
):
    filters = []

    if status is not None:
        filters.append(LoadOrder.status == status)

    if user_id is not None:
        filters.append(LoadOrder.user_id == user_id)

    if customer_id is not None:
        filters.append(LoadOrder.customer_id == customer_id)

    if active_only:
        filters.append(LoadOrder.status != LoadOrderStatus.CANCELLED)

    normalized_search = search.strip().lower() if search else ""
    if normalized_search:
        like_pattern = f"%{normalized_search}%"
        filters.append(
            or_(
                func.lower(cast(LoadOrder.id, String)).like(like_pattern),
                func.lower(func.coalesce(LoadOrder.customer_name, "")).like(like_pattern),
                func.lower(func.coalesce(LoadOrder.origin_text, "")).like(like_pattern),
                func.lower(func.coalesce(LoadOrder.destination_text, "")).like(like_pattern),
            )
        )

    return filters


def _apply_order_filters(stmt, filters):
    for filter_clause in filters:
        stmt = stmt.where(filter_clause)
    return stmt


def validate_formalization_transition(current_status: LoadOrderStatus) -> None:
    validate_load_order_transition(
        current_status,
        LoadOrderStatus.FORMALIZED,
    )


async def validate_ready_for_formalization_requires_selection(
    session: AsyncSession,
    runtime_order: LoadOrder,
) -> None:
    if runtime_order.status not in {
        LoadOrderStatus.VIABILITY_CONFIRMED,
        LoadOrderStatus.SEARCHING_CARRIER,
        LoadOrderStatus.READY_FOR_FORMALIZATION,
    }:
        return

    if runtime_order.selected_trip_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Carrier selection required before ready_for_formalization",
        )

    selected_trip = await session.get(Trip, runtime_order.selected_trip_id)
    if selected_trip is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Carrier selection required before ready_for_formalization",
        )

    if selected_trip.load_order_id != runtime_order.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Carrier selection required before ready_for_formalization",
        )

    if TripProposalStatus(selected_trip.proposal_status) != TripProposalStatus.CANDIDATE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Carrier selection required before ready_for_formalization",
        )


def _build_order_query(
    *,
    status: LoadOrderStatus | None = None,
    user_id: UUID | None = None,
    customer_id: UUID | None = None,
    active_only: bool = False,
    search: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Select[tuple[LoadOrder]]:
    stmt = select(LoadOrder).order_by(LoadOrder.created_at.desc())
    filters = _build_order_filters(
        status=status,
        user_id=user_id,
        customer_id=customer_id,
        active_only=active_only,
        search=search,
    )
    stmt = _apply_order_filters(stmt, filters)
    return stmt.offset(skip).limit(limit)


async def get_load_order_by_id(
    session: AsyncSession,
    load_order_id: UUID,
) -> LoadOrderResponse | None:
    runtime_order = await session.get(LoadOrder, load_order_id)
    if runtime_order is None:
        return None

    return _to_load_order_response(runtime_order)


async def create_load_order(
    session: AsyncSession,
    payload: LoadOrderCreate,
) -> LoadOrderResponse:
    try:
        validate_load_order_payload(payload)
    except ValueError as exc:
        raise _translate_validation_error(exc) from exc

    if is_canonical_prototype_truck_type_id(payload.truck_type_id):
        await ensure_canonical_prototype_truck_types(session)

    runtime_order = LoadOrder(**payload.model_dump())
    session.add(runtime_order)
    await session.flush()
    return _to_load_order_response(runtime_order)


async def list_load_orders(
    session: AsyncSession,
    *,
    status: LoadOrderStatus | None = None,
    user_id: UUID | None = None,
    customer_id: UUID | None = None,
    active_only: bool = False,
    search: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[LoadOrderResponse]:
    result = await session.execute(
        _build_order_query(
            status=status,
            user_id=user_id,
            customer_id=customer_id,
            active_only=active_only,
            search=search,
            skip=skip,
            limit=limit,
        )
    )
    runtime_orders = list(result.scalars().all())
    return [_to_load_order_response(runtime_order) for runtime_order in runtime_orders]


async def list_load_orders_page(
    session: AsyncSession,
    *,
    status: LoadOrderStatus | None = None,
    user_id: UUID | None = None,
    customer_id: UUID | None = None,
    active_only: bool = False,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> LoadOrderListPageResponse:
    filters = _build_order_filters(
        status=status,
        user_id=user_id,
        customer_id=customer_id,
        active_only=active_only,
        search=search,
    )

    items_result = await session.execute(
        _build_order_query(
            status=status,
            user_id=user_id,
            customer_id=customer_id,
            active_only=active_only,
            search=search,
            skip=skip,
            limit=limit,
        )
    )
    total_result = await session.execute(
        _apply_order_filters(select(func.count()).select_from(LoadOrder), filters)
    )

    runtime_orders = list(items_result.scalars().all())
    return LoadOrderListPageResponse(
        items=[_to_load_order_response(runtime_order) for runtime_order in runtime_orders],
        total=total_result.scalar_one(),
        skip=skip,
        limit=limit,
    )


async def get_dashboard_load_order_summary(
    session: AsyncSession,
    *,
    limit: int = 5,
) -> DashboardLoadOrderSummaryResponse:
    active_count_result = await session.execute(
        select(func.count())
        .select_from(LoadOrder)
        .where(LoadOrder.status != LoadOrderStatus.CANCELLED)
    )
    needs_attention_result = await session.execute(
        select(func.count())
        .select_from(LoadOrder)
        .where(LoadOrder.status.in_(_DASHBOARD_ATTENTION_STATUSES))
    )
    attention_orders_result = await session.execute(
        select(LoadOrder)
        .where(LoadOrder.status.in_(_DASHBOARD_ATTENTION_STATUSES))
        .order_by(LoadOrder.updated_at.desc(), LoadOrder.created_at.desc())
        .limit(limit)
    )
    recent_active_orders_result = await session.execute(
        select(LoadOrder)
        .where(LoadOrder.status != LoadOrderStatus.CANCELLED)
        .order_by(LoadOrder.updated_at.desc(), LoadOrder.created_at.desc())
        .limit(limit)
    )

    attention_orders = list(attention_orders_result.scalars().all())
    recent_active_orders = list(recent_active_orders_result.scalars().all())

    return DashboardLoadOrderSummaryResponse(
        active_order_count=active_count_result.scalar_one(),
        needs_attention_count=needs_attention_result.scalar_one(),
        attention_orders=[_to_dashboard_order_item(order) for order in attention_orders],
        recent_active_orders=[_to_dashboard_order_item(order) for order in recent_active_orders],
    )


async def update_load_order(
    session: AsyncSession,
    load_order_id: UUID,
    payload: LoadOrderUpdate,
) -> LoadOrderResponse:
    try:
        validate_load_order_payload(payload)
    except ValueError as exc:
        raise _translate_validation_error(exc) from exc

    runtime_order = await session.get(LoadOrder, load_order_id)
    if runtime_order is None:
        raise HTTPException(status_code=404, detail="Load order not found")

    update_data = payload.model_dump(exclude_unset=True)
    if is_canonical_prototype_truck_type_id(update_data.get("truck_type_id")):
        await ensure_canonical_prototype_truck_types(session)

    new_status = update_data.get("status")
    if new_status is not None and new_status != runtime_order.status:
        try:
            validate_load_order_transition(runtime_order.status, new_status)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        if new_status == LoadOrderStatus.READY_FOR_FORMALIZATION:
            await validate_ready_for_formalization_requires_selection(session, runtime_order)

    for field_name, value in update_data.items():
        setattr(runtime_order, field_name, value)

    await session.flush()

    return _to_load_order_response(runtime_order)


async def cancel_load_order(
    session: AsyncSession,
    load_order_id: UUID,
) -> LoadOrderResponse:
    runtime_order = await session.get(LoadOrder, load_order_id)
    if runtime_order is None:
        raise HTTPException(status_code=404, detail="Load order not found")

    if runtime_order.status != LoadOrderStatus.CANCELLED:
        try:
            validate_load_order_transition(runtime_order.status, LoadOrderStatus.CANCELLED)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    runtime_order.status = LoadOrderStatus.CANCELLED
    await session.flush()

    return _to_load_order_response(runtime_order)


async def formalize_load_order(
    session: AsyncSession,
    load_order_id: UUID,
) -> LoadOrderResponse:
    runtime_order = await session.get(LoadOrder, load_order_id)
    if runtime_order is None:
        raise HTTPException(status_code=404, detail="Load order not found")

    if runtime_order.status in {
        LoadOrderStatus.SEARCHING_CARRIER,
        LoadOrderStatus.READY_FOR_FORMALIZATION,
    }:
        # Surface the missing/invalid carrier-selection error before the generic transition error.
        await validate_ready_for_formalization_requires_selection(session, runtime_order)

    try:
        validate_formalization_transition(runtime_order.status)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    runtime_order.status = LoadOrderStatus.FORMALIZED
    await session.flush()

    return _to_load_order_response(runtime_order)


async def get_load_order_or_404(
    session: AsyncSession,
    load_order_id: UUID,
) -> LoadOrderResponse:
    runtime_order = await session.get(LoadOrder, load_order_id)
    if runtime_order is None:
        raise HTTPException(status_code=404, detail="Load order not found")

    return _to_load_order_response(runtime_order)


async def delete_load_order(
    session: AsyncSession,
    load_order_id: UUID,
) -> None:
    runtime_order = await session.get(LoadOrder, load_order_id)
    if runtime_order is None:
        raise HTTPException(status_code=404, detail="Load order not found")

    await session.execute(delete(MonitoringAlert).where(MonitoringAlert.load_order_id == load_order_id))
    await session.execute(delete(ExecutionMonitoringSnapshot).where(ExecutionMonitoringSnapshot.load_order_id == load_order_id))
    await session.execute(delete(Trip).where(Trip.load_order_id == load_order_id))
    await session.execute(delete(AgentActivity).where(AgentActivity.load_order_id == load_order_id))
    await session.execute(delete(LoadOrderHumanReview).where(LoadOrderHumanReview.load_order_id == load_order_id))
    await session.execute(delete(IngestionRun).where(IngestionRun.load_order_id == load_order_id))

    await session.delete(runtime_order)
    await session.flush()
