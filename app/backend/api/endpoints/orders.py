from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.backend.api.dependencies.auth import CurrentUserDep, get_current_user
from app.backend.core.domain_enums import LoadOrderStatus
from app.backend.db.session import AsyncSessionDep
from app.backend.models.load_order import LoadOrder
from app.backend.schemas.load_order import (
    DashboardLoadOrderSummaryResponse,
    LoadOrderCreate,
    LoadOrderCreateRequest,
    LoadOrderListPageResponse,
    LoadOrderResponse,
    LoadOrderUpdate,
)
from app.backend.schemas.human_validation import (
    HumanValidationConfirmRequest,
    HumanValidationConfirmRequestBrowser,
    HumanValidationContextResponse,
    HumanValidationUpdateRequest,
    HumanValidationUpdateRequestBrowser,
)
from app.backend.schemas.agents import AgentActivityResponse
from app.backend.schemas.carrier_search import CarrierSearchResponse, CarrierSelectionRequest
from app.backend.schemas.orchestrator import (
    OrchestratorDelegationRequest,
    OrchestratorDelegationResponse,
)
from app.backend.services.load_order_carrier_selection import select_load_order_carrier
from app.backend.services.load_order_carrier_search import (
    create_load_order_carrier_search,
    get_load_order_carrier_candidates,
)
from app.backend.services.load_orders import (
    cancel_load_order,
    create_load_order,
    delete_load_order,
    derive_manual_create_defaults,
    get_dashboard_load_order_summary,
    formalize_load_order,
    get_load_order_or_404,
    list_load_orders,
    list_load_orders_page,
    update_load_order,
)
from app.backend.services.load_order_human_validation import (
    confirm_load_order_viability,
    get_load_order_human_validation_context,
    update_load_order_human_validation,
)
from app.backend.services.load_order_orchestrator import (
    log_auto_carrier_search_triggered,
    log_carrier_search_agent_dispatched,
    log_carrier_search_agent_completed,
    log_carrier_search_completed,
    log_carrier_selection_cleared,
    log_carrier_selected,
    log_orchestrator_manual_refresh,
    log_order_cancelled,
    log_order_created,
    log_order_formalized,
    log_viability_confirmed,
)
from app.backend.services.delegated_orchestrator import delegate_operator_request
from app.backend.services.execution_monitoring import ensure_execution_monitoring_snapshot

router = APIRouter(
    prefix="/orders",
    tags=["Load Orders"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/", response_model=LoadOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: LoadOrderCreateRequest,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
) -> LoadOrderResponse:
    payload_data = payload.model_dump(exclude_unset=True)
    if "status" not in payload_data and "missing_fields" not in payload_data:
        _MANUAL_CREATE_REQUIRED_FIELDS = (
            "customer_name",
            "origin_text",
            "destination_text",
            "origin_load_date",
            "cargo_description",
        )
        missing_required = [
            field
            for field in _MANUAL_CREATE_REQUIRED_FIELDS
            if not payload_data.get(field)
        ]
        if missing_required:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing required fields: {', '.join(missing_required)}",
            )
        derived_status, derived_missing_fields = derive_manual_create_defaults(payload)
        payload_data["status"] = derived_status
        payload_data["missing_fields"] = derived_missing_fields

    internal_payload = LoadOrderCreate(
        user_id=current_user.id,
        **payload_data,
    )
    new_order = await create_load_order(session, internal_payload)

    from app.backend.models.load_order import LoadOrder
    runtime_order = await session.get(LoadOrder, new_order.id)
    if runtime_order is not None:
        await log_order_created(session, runtime_order)
        if runtime_order.status == LoadOrderStatus.VIABILITY_CONFIRMED:
            await log_viability_confirmed(session, runtime_order)

    await session.commit()
    return new_order


@router.get("/", response_model=list[LoadOrderResponse])
async def list_orders(
    session: AsyncSessionDep,
    status: LoadOrderStatus | None = None,
    user_id: UUID | None = None,
    customer_id: UUID | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[LoadOrderResponse]:
    return await list_load_orders(
        session,
        status=status,
        user_id=user_id,
        customer_id=customer_id,
        skip=skip,
        limit=limit,
    )


@router.get("/page", response_model=LoadOrderListPageResponse)
async def list_orders_page_endpoint(
    session: AsyncSessionDep,
    status: LoadOrderStatus | None = None,
    user_id: UUID | None = None,
    customer_id: UUID | None = None,
    active_only: bool = False,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> LoadOrderListPageResponse:
    return await list_load_orders_page(
        session,
        status=status,
        user_id=user_id,
        customer_id=customer_id,
        active_only=active_only,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get("/summary", response_model=DashboardLoadOrderSummaryResponse)
async def get_dashboard_load_order_summary_endpoint(
    session: AsyncSessionDep,
    limit: int = Query(default=5, ge=1, le=10),
) -> DashboardLoadOrderSummaryResponse:
    return await get_dashboard_load_order_summary(session, limit=limit)


@router.get("/geocode/distance")
async def geocode_distance_endpoint(
    origin: str = Query(..., min_length=1),
    destination: str = Query(..., min_length=1),
) -> dict[str, float]:
    from app.backend.services.execution_monitoring import (
        _distance_between_coordinates,
        _resolve_coordinate_for_label,
    )

    origin_coord, _ = await _resolve_coordinate_for_label(origin, fallback_seed=0)
    dest_coord, _ = await _resolve_coordinate_for_label(destination, fallback_seed=1)

    distance = _distance_between_coordinates(
        (origin_coord["lat"], origin_coord["lng"]),
        (dest_coord["lat"], dest_coord["lng"]),
    )

    return {"distance_km": round(distance, 2)}


@router.get("/{order_id}", response_model=LoadOrderResponse)
async def get_order(
    order_id: UUID,
    session: AsyncSessionDep,
) -> LoadOrderResponse:
    return await get_load_order_or_404(session, order_id)


@router.post("/{order_id}/orchestrator-refresh", response_model=AgentActivityResponse)
async def refresh_order_orchestrator_endpoint(
    order_id: UUID,
    session: AsyncSessionDep,
) -> AgentActivityResponse:
    order = await get_load_order_or_404(session, order_id)
    activity = await log_orchestrator_manual_refresh(session, order)
    await session.commit()
    await session.refresh(activity)
    return AgentActivityResponse.model_validate(activity)


@router.post("/delegated-actions", response_model=OrchestratorDelegationResponse)
async def delegate_order_action_endpoint(
    payload: OrchestratorDelegationRequest,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
) -> OrchestratorDelegationResponse:
    result = await delegate_operator_request(
        session,
        user_id=current_user.id,
        payload=payload,
    )
    await session.commit()
    return result


@router.get("/{order_id}/human-validation", response_model=HumanValidationContextResponse)
async def get_order_human_validation_context(
    order_id: UUID,
    session: AsyncSessionDep,
) -> HumanValidationContextResponse:
    return await get_load_order_human_validation_context(session, order_id)


@router.put("/{order_id}", response_model=LoadOrderResponse)
async def update_order_endpoint(
    order_id: UUID,
    payload: LoadOrderUpdate,
    session: AsyncSessionDep,
) -> LoadOrderResponse:
    order = await update_load_order(session, order_id, payload)
    await session.commit()
    return order


@router.put("/{order_id}/human-validation", response_model=HumanValidationContextResponse)
async def update_order_human_validation_endpoint(
    order_id: UUID,
    payload: HumanValidationUpdateRequestBrowser,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
) -> HumanValidationContextResponse:
    internal_payload = HumanValidationUpdateRequest(
        reviewed_by_user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )
    context = await update_load_order_human_validation(session, order_id, internal_payload)
    await session.commit()
    return context


@router.post("/{order_id}/cancel", response_model=LoadOrderResponse)
async def cancel_order_endpoint(
    order_id: UUID,
    session: AsyncSessionDep,
) -> LoadOrderResponse:
    order = await cancel_load_order(session, order_id)
    runtime_order = await session.get(LoadOrder, order_id)
    await log_order_cancelled(session, runtime_order)
    await session.commit()
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order_endpoint(
    order_id: UUID,
    session: AsyncSessionDep,
) -> Response:
    await delete_load_order(session, order_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{order_id}/formalize", response_model=LoadOrderResponse)
async def formalize_order_endpoint(
    order_id: UUID,
    session: AsyncSessionDep,
) -> LoadOrderResponse:
    from app.backend.core.domain_enums import AgentActivityState, AgentKind
    from app.backend.services.agent_activity_log import append_agent_activity

    order = await formalize_load_order(session, order_id)
    runtime_order = await session.get(LoadOrder, order_id)
    await log_order_formalized(session, runtime_order)
    if runtime_order is not None:
        await append_agent_activity(
            session,
            agent_kind=AgentKind.MONITORING,
            activity_state=AgentActivityState.RUNNING,
            title="Shipment monitoring initializing",
            detail="Execution monitoring snapshot is being generated for the formalized order.",
            activity_key="monitoring_started",
            load_order_id=runtime_order.id,
        )
        await session.commit()

        await ensure_execution_monitoring_snapshot(session, runtime_order, source="order_formalized")

        await append_agent_activity(
            session,
            agent_kind=AgentKind.MONITORING,
            activity_state=AgentActivityState.COMPLETED,
            title="Shipment monitoring active",
            detail="Geocoding, routing, and initial trip simulation completed.",
            activity_key="monitoring_initialized",
            load_order_id=runtime_order.id,
        )
    await session.commit()
    return order


@router.post("/{order_id}/confirm-viability", response_model=LoadOrderResponse)
async def confirm_order_viability_endpoint(
    order_id: UUID,
    payload: HumanValidationConfirmRequestBrowser,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
) -> LoadOrderResponse:
    internal_payload = HumanValidationConfirmRequest(
        reviewed_by_user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )
    order = await confirm_load_order_viability(session, order_id, internal_payload)
    runtime_order = await session.get(LoadOrder, order_id)
    await log_viability_confirmed(session, runtime_order)

    if runtime_order is not None:
        try:
            from app.backend.services.runtime_settings import load_boolean_settings
            bool_settings = await load_boolean_settings(session)
            if bool_settings.get("enable_auto_carrier_search"):
                from app.backend.services.load_order_carrier_search import (
                    create_load_order_carrier_search,
                    list_load_order_trips,
                )
                existing_trips = await list_load_order_trips(session, order_id)
                if (
                    not existing_trips
                    and runtime_order.distance_km is not None
                    and runtime_order.customer_price is not None
                ):
                    carrier_search, created = await create_load_order_carrier_search(session, order_id)
                    if created:
                        await log_auto_carrier_search_triggered(session, runtime_order)
                        await log_carrier_search_agent_dispatched(session, runtime_order)
                        await log_carrier_search_completed(
                            session, runtime_order, candidate_count=len(carrier_search.candidates)
                        )
                        await log_carrier_search_agent_completed(
                            session, runtime_order, candidate_count=len(carrier_search.candidates)
                        )
        except Exception:
            pass

    await session.commit()
    return order


@router.post(
    "/{order_id}/carrier-search",
    response_model=CarrierSearchResponse,
    responses={
        status.HTTP_201_CREATED: {"model": CarrierSearchResponse},
    },
)
async def create_order_carrier_search_endpoint(
    order_id: UUID,
    response: Response,
    session: AsyncSessionDep,
) -> CarrierSearchResponse:
    carrier_search, created = await create_load_order_carrier_search(session, order_id)
    if created:
        runtime_order = await session.get(LoadOrder, order_id)
        if runtime_order is not None:
            await log_carrier_search_agent_dispatched(session, runtime_order)
            await log_carrier_search_completed(
                session, runtime_order, candidate_count=len(carrier_search.candidates)
            )
            await log_carrier_search_agent_completed(
                session, runtime_order, candidate_count=len(carrier_search.candidates)
            )
    await session.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return carrier_search


@router.get("/{order_id}/carrier-candidates", response_model=CarrierSearchResponse)
async def get_order_carrier_candidates_endpoint(
    order_id: UUID,
    session: AsyncSessionDep,
) -> CarrierSearchResponse:
    return await get_load_order_carrier_candidates(session, order_id)


@router.put("/{order_id}/carrier-selection", response_model=CarrierSearchResponse)
async def select_order_carrier_endpoint(
    order_id: UUID,
    payload: CarrierSelectionRequest,
    session: AsyncSessionDep,
) -> CarrierSearchResponse:
    carrier_search = await select_load_order_carrier(session, order_id, payload.trip_id)

    runtime_order = await session.get(LoadOrder, order_id)
    if runtime_order is not None:
        if payload.trip_id is None:
            await log_carrier_selection_cleared(session, runtime_order)
        else:
            selected_candidate = next(
                (c for c in carrier_search.candidates if c.trip_id == payload.trip_id),
                None,
            )
            carrier_name = selected_candidate.company_name if selected_candidate else "Unknown"
            await log_carrier_selected(session, runtime_order, carrier_name=carrier_name)

            if selected_candidate is not None:
                try:
                    from app.backend.services.rag_memory import index_carrier_decision_memory
                    index_carrier_decision_memory(
                        order_id=str(runtime_order.id),
                        origin=runtime_order.origin_text or "unknown",
                        destination=runtime_order.destination_text or "unknown",
                        adr_required=runtime_order.adr_required,
                        truck_type=str(runtime_order.truck_type_id) if runtime_order.truck_type_id else "any",
                        customer_price=str(runtime_order.customer_price) if runtime_order.customer_price else "0",
                        selected_carrier=carrier_name,
                        carrier_price=str(selected_candidate.carrier_price) if selected_candidate.carrier_price else "0",
                        margin=str(selected_candidate.profit_margin) if selected_candidate.profit_margin else "0",
                    )
                except Exception:
                    pass

    await session.commit()
    return carrier_search
