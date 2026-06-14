"""API endpoints for agent status and orchestrator timeline."""

from fastapi import APIRouter, Depends, Query

from app.backend.api.dependencies.auth import get_current_user
from app.backend.db.session import AsyncSessionDep
from app.backend.schemas.agents import AgentStatusListResponse, OrchestratorTimelineItem
from app.backend.services.agent_activity_log import get_agent_statuses, get_orchestrator_timeline

router = APIRouter(
    prefix="/agents",
    tags=["Agents"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/status", response_model=AgentStatusListResponse)
async def get_agent_statuses_endpoint(
    session: AsyncSessionDep,
) -> AgentStatusListResponse:
    """Return one dashboard card payload per agent kind."""
    statuses = await get_agent_statuses(session)
    return AgentStatusListResponse(agents=statuses)


@router.get("/orchestrator/timeline", response_model=list[OrchestratorTimelineItem])
async def get_orchestrator_timeline_endpoint(
    session: AsyncSessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    load_order_id: str | None = Query(default=None),
) -> list[OrchestratorTimelineItem]:
    """Return recent orchestrator timeline items for the dashboard."""
    from uuid import UUID

    parsed_order_id = UUID(load_order_id) if load_order_id else None
    return await get_orchestrator_timeline(session, limit=limit, load_order_id=parsed_order_id)
