"""Orchestrator decision service — thin event-driven logging layer."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.domain_enums import AgentActivityState, AgentKind, LoadOrderStatus
from app.backend.core.settings import Settings, get_settings
from app.backend.models.load_order import LoadOrder
from app.backend.services.agent_activity_log import append_agent_activity


class OrchestratorDecision(BaseModel):
    workflow_interpretation: str
    next_action: str
    action_owner: str  # "operator" or "agent"
    explanation: str

    model_config = {"extra": "forbid"}


_ALLOWED_NEXT_ACTIONS = frozenset({
    "run_ingestion",
    "await_operator_review",
    "run_carrier_search",
    "await_carrier_selection",
    "formalize_order",
    "cancel_order",
    "await_operator",
    "notify_operator",
})

_ALLOWED_ACTION_OWNERS = frozenset({"operator", "agent"})

_FALLBACK_DECISION = OrchestratorDecision(
    workflow_interpretation="undetermined",
    next_action="await_operator",
    action_owner="operator",
    explanation="Fallback: model output was invalid or unavailable.",
)


@dataclass(frozen=True)
class OrchestratorDecisionEnvelope:
    decision: OrchestratorDecision
    metadata: dict[str, object]


def _parse_orchestrator_decision(raw: dict) -> tuple[OrchestratorDecision, bool]:
    try:
        decision = OrchestratorDecision(**raw)
    except Exception:
        return _FALLBACK_DECISION, False

    if decision.next_action not in _ALLOWED_NEXT_ACTIONS:
        return _FALLBACK_DECISION, False

    if decision.action_owner not in _ALLOWED_ACTION_OWNERS:
        return _FALLBACK_DECISION, False

    return decision, True


def _validate_orchestrator_decision(raw: dict) -> OrchestratorDecision:
    return _parse_orchestrator_decision(raw)[0]


def _format_next_action_label(next_action: str) -> str:
    return next_action.replace("_", " ").capitalize()


def _activity_state_for_owner(action_owner: str, default_state: AgentActivityState) -> AgentActivityState:
    if action_owner == "operator":
        return AgentActivityState.AWAITING_OPERATOR
    return default_state


def _decision_fields(
    extra: dict[str, object] | None,
    *,
    default_detail: str,
    default_next_action: str | None,
    default_state: AgentActivityState,
) -> tuple[str, str | None, AgentActivityState]:
    if extra is None:
        return default_detail, default_next_action, default_state

    detail = str(extra.get("model_explanation") or default_detail)
    raw_next_action = extra.get("model_next_action")
    next_action = (
        _format_next_action_label(str(raw_next_action))
        if isinstance(raw_next_action, str) and raw_next_action
        else default_next_action
    )
    owner = extra.get("model_action_owner")
    state = (
        _activity_state_for_owner(owner, default_state)
        if isinstance(owner, str)
        else default_state
    )
    return detail, next_action, state


async def generate_orchestrator_decision_envelope(
    *,
    settings: Settings,
    order_status: LoadOrderStatus,
) -> OrchestratorDecisionEnvelope:
    from app.backend.services.model_runtime_gateway import structured_completion

    base_metadata: dict[str, object] = {
        "provider": settings.reasoning_model_provider,
        "model_name": settings.reasoning_model_name,
        "runtime_profile": "reasoning",
    }

    try:
        result = await structured_completion(
            settings=settings,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the Hermes orchestrator. Given a load order status, "
                        "decide the next workflow action in a conservative, operations-safe way. Return valid JSON with keys: "
                        "workflow_interpretation, next_action, action_owner, explanation. "
                        "next_action must be one of: run_ingestion, await_operator_review, "
                        "run_carrier_search, await_carrier_selection, formalize_order, "
                        "cancel_order, await_operator, notify_operator. "
                        "action_owner must be 'operator' or 'agent'. "
                        "Do not invent hidden state transitions, approvals, or completed work. "
                        "Base the answer strictly on the provided status."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Current order status: {order_status.value}. What is the next action?",
                },
            ],
            profile="reasoning",
        )
    except Exception:
        return OrchestratorDecisionEnvelope(
            decision=_FALLBACK_DECISION,
            metadata={
                **base_metadata,
                "execution_path": "fallback",
                "fallback_reason": "runtime_error",
                "workflow_interpretation": _FALLBACK_DECISION.workflow_interpretation,
                "model_next_action": _FALLBACK_DECISION.next_action,
                "model_action_owner": _FALLBACK_DECISION.action_owner,
                "model_explanation": _FALLBACK_DECISION.explanation,
            },
        )

    decision, is_valid = _parse_orchestrator_decision(result.content)
    metadata = {
        **base_metadata,
        "execution_path": "cloud" if is_valid else "fallback",
        "workflow_interpretation": decision.workflow_interpretation,
        "model_next_action": decision.next_action,
        "model_action_owner": decision.action_owner,
        "model_explanation": decision.explanation,
    }
    if not is_valid:
        metadata["fallback_reason"] = "invalid_output"

    return OrchestratorDecisionEnvelope(decision=decision, metadata=metadata)


async def generate_orchestrator_decision(
    *,
    settings: Settings,
    order_status: LoadOrderStatus,
) -> OrchestratorDecision:
    envelope = await generate_orchestrator_decision_envelope(
        settings=settings,
        order_status=order_status,
    )
    return envelope.decision


async def _gather_cloud_decision_metadata(order_status: LoadOrderStatus) -> dict[str, object] | None:
    settings = get_settings()
    if not settings.reasoning_model_name:
        return None

    envelope = await generate_orchestrator_decision_envelope(
        settings=settings,
        order_status=order_status,
    )
    return envelope.metadata


async def log_order_created(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log that a new order was created and dispatched to ingestion."""
    customer = order.customer_name or "Unknown customer"
    detail = f"Origin: {order.origin_text or 'TBD'} -> Destination: {order.destination_text or 'TBD'}"
    extra = await _gather_cloud_decision_metadata(order.status)
    detail, next_action, state = _decision_fields(
        extra,
        default_detail=detail,
        default_next_action="Dispatched ingestion agent",
        default_state=AgentActivityState.COMPLETED,
    )
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=state,
        title=f"New order received from {customer}",
        detail=detail,
        activity_key="order_created",
        load_order_id=order.id,
        next_action=next_action,
        extra_metadata=extra,
    )


async def log_ingestion_completed(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log that ingestion extraction completed for an order."""
    extra = await _gather_cloud_decision_metadata(order.status)
    detail, next_action, state = _decision_fields(
        extra,
        default_detail="Data extraction finished. Operator review required.",
        default_next_action="Operator review required",
        default_state=AgentActivityState.AWAITING_OPERATOR,
    )
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=state,
        title="Ingestion completed — awaiting operator review",
        detail=detail,
        activity_key="ingestion_completed",
        load_order_id=order.id,
        next_action=next_action,
        extra_metadata=extra,
    )


async def log_viability_confirmed(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log that operator confirmed viability and carrier search will start."""
    extra = await _gather_cloud_decision_metadata(order.status)
    detail, next_action, state = _decision_fields(
        extra,
        default_detail="Operator confirmed order viability.",
        default_next_action="Carrier search dispatched",
        default_state=AgentActivityState.COMPLETED,
    )
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=state,
        title="Viability confirmed — dispatching carrier search",
        detail=detail,
        activity_key="viability_confirmed",
        load_order_id=order.id,
        next_action=next_action,
        extra_metadata=extra,
    )


async def log_carrier_search_dispatched(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log that carrier search was dispatched for an order."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=AgentActivityState.RUNNING,
        title="Carrier search in progress",
        detail="Searching for optimal carrier candidates.",
        activity_key="carrier_search_dispatched",
        load_order_id=order.id,
        next_action="Awaiting carrier search results",
    )


async def log_carrier_search_completed(
    session: AsyncSession,
    order: LoadOrder,
    *,
    candidate_count: int,
):
    """Log that carrier search completed with candidate count."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=AgentActivityState.AWAITING_OPERATOR,
        title=f"Carrier search completed — {candidate_count} candidates ranked",
        detail=f"Found and ranked {candidate_count} carrier candidates.",
        activity_key="carrier_search_completed",
        load_order_id=order.id,
        next_action="Operator selects carrier",
    )


async def log_carrier_selected(
    session: AsyncSession,
    order: LoadOrder,
    *,
    carrier_name: str,
):
    """Log that a carrier was selected for the order."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=AgentActivityState.AWAITING_OPERATOR,
        title=f"Carrier selected: {carrier_name}",
        detail=f"Operator selected {carrier_name} for this shipment.",
        activity_key="carrier_selected",
        load_order_id=order.id,
        next_action="Ready for formalization",
    )


async def log_carrier_selection_cleared(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log that the operator cleared a previously selected carrier."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=AgentActivityState.AWAITING_OPERATOR,
        title="Carrier selection cleared",
        detail="Operator cleared the current carrier selection.",
        activity_key="carrier_selection_cleared",
        load_order_id=order.id,
        next_action="Select carrier",
    )


async def log_order_cancelled(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log that an order was cancelled."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=AgentActivityState.COMPLETED,
        title="Order cancelled",
        detail="Order was cancelled by operator.",
        activity_key="order_cancelled",
        load_order_id=order.id,
    )


async def log_order_formalized(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log that an order was formalized."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=AgentActivityState.COMPLETED,
        title="Order formalized — execution handoff complete",
        detail="Order moved from booking workflow into shipment execution monitoring.",
        activity_key="order_formalized",
        load_order_id=order.id,
    )


async def log_orchestrator_manual_refresh(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log an explicit operator-triggered orchestrator reevaluation."""
    extra = await _gather_cloud_decision_metadata(order.status)
    default_detail = f"Manual refresh evaluated current workflow state: {order.status.value}."
    detail, next_action, state = _decision_fields(
        extra,
        default_detail=default_detail,
        default_next_action="Review workflow state",
        default_state=AgentActivityState.COMPLETED,
    )
    if detail != default_detail:
        detail = f"{default_detail} {detail}"
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=state,
        title="Manual orchestrator refresh completed",
        detail=detail,
        activity_key="orchestrator_manual_refresh",
        load_order_id=order.id,
        next_action=next_action,
        extra_metadata=extra,
    )


async def log_ingestion_agent_completed(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log ingestion subsystem activity for dashboard visibility."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.INGESTION,
        activity_state=AgentActivityState.COMPLETED,
        title="Extraction completed",
        detail="Raw text extracted and structured by ingestion agent.",
        activity_key="ingestion_extraction_completed",
        load_order_id=order.id,
    )


async def log_carrier_search_agent_dispatched(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log carrier search subsystem activity for dashboard visibility."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.CARRIER_SEARCH,
        activity_state=AgentActivityState.RUNNING,
        title="Carrier search dispatched",
        detail="Search agent running carrier market analysis.",
        activity_key="carrier_search_agent_dispatched",
        load_order_id=order.id,
    )


async def log_carrier_search_agent_completed(
    session: AsyncSession,
    order: LoadOrder,
    *,
    candidate_count: int,
):
    """Log carrier search completion subsystem activity for dashboard visibility."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.CARRIER_SEARCH,
        activity_state=AgentActivityState.COMPLETED,
        title=f"Carrier search finished — {candidate_count} results",
        detail=f"Carrier search agent found {candidate_count} candidates.",
        activity_key="carrier_search_agent_completed",
        load_order_id=order.id,
    )


async def log_auto_carrier_search_triggered(
    session: AsyncSession,
    order: LoadOrder,
):
    """Log that carrier search was auto-triggered by the orchestrator."""
    return await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=AgentActivityState.COMPLETED,
        title="Auto carrier search triggered",
        detail="Orchestrator automatically dispatched carrier search after viability confirmation.",
        activity_key="auto_carrier_search_triggered",
        load_order_id=order.id,
        next_action="Review ranked carriers",
    )
