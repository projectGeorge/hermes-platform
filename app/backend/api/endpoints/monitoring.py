"""API endpoints for execution monitoring."""

from fastapi import APIRouter, Depends, HTTPException

from app.backend.api.dependencies.auth import get_current_user
from app.backend.core.domain_enums import AgentActivityState, AgentKind
from app.backend.db.session import AsyncSessionDep
from app.backend.models.load_order import LoadOrder
from app.backend.schemas.monitoring import ExecutionMonitoringReadModelResponse
from app.backend.services.agent_activity_log import append_agent_activity
from app.backend.services.execution_monitoring import (
    get_execution_monitoring_read_model,
    refresh_execution_monitoring_snapshot,
)
from app.backend.services.load_orders import get_load_order_or_404

router = APIRouter(
    prefix="/monitoring",
    tags=["Monitoring"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/orders/{order_id}/execution", response_model=ExecutionMonitoringReadModelResponse)
async def get_order_execution_monitoring_endpoint(
    order_id: str,
    session: AsyncSessionDep,
) -> ExecutionMonitoringReadModelResponse:
    from uuid import UUID

    return await get_execution_monitoring_read_model(session, UUID(order_id))


@router.post("/orders/{order_id}/refresh", response_model=ExecutionMonitoringReadModelResponse)
async def refresh_order_execution_monitoring_endpoint(
    order_id: str,
    session: AsyncSessionDep,
) -> ExecutionMonitoringReadModelResponse:
    from uuid import UUID

    parsed_order_id = UUID(order_id)
    await get_load_order_or_404(session, parsed_order_id)
    order = await session.get(LoadOrder, parsed_order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Load order not found")

    await append_agent_activity(
        session,
        agent_kind=AgentKind.MONITORING,
        activity_state=AgentActivityState.RUNNING,
        title="Shipment monitoring refreshing",
        detail="Execution monitoring agent is advancing simulation and regenerating route data.",
        activity_key="monitoring_refresh_started",
        load_order_id=order.id,
    )
    await session.commit()

    await refresh_execution_monitoring_snapshot(
        session,
        order,
        source="operator_refresh",
        allow_cloud_reasoning=True,
    )

    await append_agent_activity(
        session,
        agent_kind=AgentKind.MONITORING,
        activity_state=AgentActivityState.COMPLETED,
        title="Shipment monitoring refreshed",
        detail="Simulation advanced, route data and incident detection updated.",
        activity_key="monitoring_refresh_completed",
        load_order_id=order.id,
    )

    await session.commit()
    return await get_execution_monitoring_read_model(session, parsed_order_id)
