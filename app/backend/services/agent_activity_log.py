"""Shared agent activity log service for dashboard visibility."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.domain_enums import AgentActivityState, AgentKind
from app.backend.models.agent_activity import AgentActivity
from app.backend.models.load_order import LoadOrder
from app.backend.schemas.agents import AgentStatusResponse, OrchestratorTimelineItem

_AGENT_DISPLAY_NAMES: dict[AgentKind, str] = {
    AgentKind.ORCHESTRATOR: "Orchestrator",
    AgentKind.INGESTION: "Ingestion",
    AgentKind.CARRIER_SEARCH: "Carrier Search",
    AgentKind.SMART_COMMS: "Smart Comms",
    AgentKind.MONITORING: "Monitoring",
}

_DEFAULT_HEADLINE: dict[AgentKind, str] = {
    AgentKind.ORCHESTRATOR: "No activity yet",
    AgentKind.INGESTION: "No ingestion runs",
    AgentKind.CARRIER_SEARCH: "No searches performed",
    AgentKind.SMART_COMMS: "No conversations",
    AgentKind.MONITORING: "Shipment monitoring available",
}


async def append_agent_activity(
    session: AsyncSession,
    *,
    agent_kind: AgentKind,
    activity_state: AgentActivityState,
    title: str,
    activity_key: str,
    detail: str | None = None,
    load_order_id: UUID | None = None,
    next_action: str | None = None,
    extra_metadata: dict[str, object] | None = None,
) -> AgentActivity:
    """Append one row to the agent activity log."""
    activity = AgentActivity(
        agent_kind=agent_kind,
        activity_state=activity_state,
        title=title,
        activity_key=activity_key,
        detail=detail,
        load_order_id=load_order_id,
        next_action=next_action,
        extra_metadata=extra_metadata,
    )
    session.add(activity)
    await session.flush()
    return activity


async def get_agent_statuses(session: AsyncSession, user_id: UUID | None = None) -> list[AgentStatusResponse]:
    """Derive dashboard agent status cards from latest activities."""
    statuses: list[AgentStatusResponse] = []

    for agent_kind in AgentKind:
        stmt = (
            select(AgentActivity)
            .where(AgentActivity.agent_kind == agent_kind)
        )
        
        if user_id is not None:
            stmt = stmt.join(LoadOrder, AgentActivity.load_order_id == LoadOrder.id, isouter=True).where(
                (AgentActivity.load_order_id.is_(None)) | (LoadOrder.user_id == user_id)
            )
        
        stmt = stmt.order_by(AgentActivity.created_at.desc()).limit(1)
        result = await session.execute(stmt)
        latest = result.scalar_one_or_none()

        if latest is None:
            statuses.append(
                AgentStatusResponse(
                    agent_kind=agent_kind,
                    display_name=_AGENT_DISPLAY_NAMES[agent_kind],
                    state=AgentActivityState.COMPLETED,
                    headline=_DEFAULT_HEADLINE[agent_kind],
                    last_activity_at=None,
                    active_item_count=0,
                )
            )
        else:
            count_stmt = (
                select(func.count())
                .select_from(AgentActivity)
                .where(
                    AgentActivity.agent_kind == agent_kind,
                    AgentActivity.activity_state.in_([
                        AgentActivityState.RUNNING,
                        AgentActivityState.AWAITING_OPERATOR,
                    ]),
                )
            )
            
            if user_id is not None:
                count_stmt = count_stmt.join(LoadOrder, AgentActivity.load_order_id == LoadOrder.id, isouter=True).where(
                    (AgentActivity.load_order_id.is_(None)) | (LoadOrder.user_id == user_id)
                )
            
            count_result = await session.execute(count_stmt)
            active_count = count_result.scalar() or 0

            statuses.append(
                AgentStatusResponse(
                    agent_kind=agent_kind,
                    display_name=_AGENT_DISPLAY_NAMES[agent_kind],
                    state=AgentActivityState(latest.activity_state),
                    headline=latest.title,
                    last_activity_at=latest.created_at,
                    active_item_count=active_count,
                )
            )

    return statuses


async def get_orchestrator_timeline(
    session: AsyncSession,
    *,
    limit: int = 20,
    load_order_id: UUID | None = None,
    user_id: UUID | None = None,
) -> list[OrchestratorTimelineItem]:
    """Return recent orchestrator timeline items with linked order metadata."""
    stmt = (
        select(AgentActivity, LoadOrder)
        .outerjoin(LoadOrder, AgentActivity.load_order_id == LoadOrder.id)
        .order_by(AgentActivity.created_at.desc())
        .limit(limit)
    )

    if load_order_id is not None:
        stmt = stmt.where(AgentActivity.load_order_id == load_order_id)
    
    if user_id is not None:
        stmt = stmt.where(
            (AgentActivity.load_order_id.is_(None)) | (LoadOrder.user_id == user_id)
        )

    result = await session.execute(stmt)
    rows = result.all()

    items: list[OrchestratorTimelineItem] = []
    for activity, order in rows:
        route_summary = None
        if order is not None:
            parts = []
            if order.origin_text:
                parts.append(order.origin_text)
            if order.destination_text:
                parts.append(order.destination_text)
            route_summary = " → ".join(parts) if parts else None

        items.append(
            OrchestratorTimelineItem(
                agent=AgentKind(activity.agent_kind),
                title=activity.title,
                detail=activity.detail,
                next_action=activity.next_action,
                load_order_id=activity.load_order_id,
                customer_name=order.customer_name if order is not None else None,
                route_summary=route_summary,
                order_status=order.status if order is not None else None,
                created_at=activity.created_at,
            )
        )

    return items
