"""Delegated orchestrator service for explicit operator intents."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.domain_enums import (
    AgentActivityState,
    AgentKind,
    LoadOrderStatus,
    SmartCommsContextType,
)
from app.backend.models.load_order import LoadOrder
from app.backend.schemas.agents import AgentActivityResponse
from app.backend.schemas.orchestrator import (
    OrchestratorDelegationRequest,
    OrchestratorDelegationResponse,
)
from app.backend.schemas.smart_comms import SmartCommsConversationResponse
from app.backend.services.agent_activity_log import append_agent_activity
from app.backend.services.execution_monitoring import (
    ensure_execution_monitoring_snapshot,
    get_execution_monitoring_read_model,
)
from app.backend.services.load_order_carrier_search import create_load_order_carrier_search
from app.backend.services.load_order_ingestion import ingest_load_order_from_raw_text
from app.backend.services.runtime_settings import load_boolean_settings
from app.backend.services.smart_comms_service import persist_assistant_message, resolve_conversation


def _delegation_metadata(
    *,
    action: str,
    delegated_to: str,
    load_order_id: UUID | None,
) -> dict[str, object]:
    return {
        "delegated_action": action,
        "delegated_to": delegated_to,
        "load_order_id": str(load_order_id) if load_order_id else None,
        "runtime_profile": "explicit_operator_action",
        "execution_path": "manual_trigger",
    }


async def _require_runtime_order(session: AsyncSession, load_order_id: UUID | None) -> LoadOrder:
    if load_order_id is None:
        raise HTTPException(status_code=422, detail="load_order_id is required for this delegated action")

    order = await session.get(LoadOrder, load_order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Load order not found")
    return order


def _require_formalized_for_monitoring(order: LoadOrder) -> None:
    if order.status != LoadOrderStatus.FORMALIZED:
        raise HTTPException(
            status_code=409,
            detail="Shipment monitoring is only available after the order is formalized",
        )


async def _log_delegation(
    session: AsyncSession,
    *,
    load_order_id: UUID | None,
    title: str,
    detail: str,
    activity_key: str,
    next_action: str | None,
    delegated_to: str,
    action: str,
) -> AgentActivityResponse:
    activity = await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=AgentActivityState.COMPLETED,
        title=title,
        detail=detail,
        activity_key=activity_key,
        load_order_id=load_order_id,
        next_action=next_action,
        extra_metadata=_delegation_metadata(
            action=action,
            delegated_to=delegated_to,
            load_order_id=load_order_id,
        ),
    )
    return AgentActivityResponse.model_validate(activity)


async def delegate_operator_request(
    session: AsyncSession,
    *,
    user_id: UUID,
    payload: OrchestratorDelegationRequest,
) -> OrchestratorDelegationResponse:
    if payload.action == "extract_email_into_order_draft":
        if not payload.source_email_text:
            raise HTTPException(status_code=422, detail="source_email_text is required for email extraction")

        await append_agent_activity(
            session,
            agent_kind=AgentKind.INGESTION,
            activity_state=AgentActivityState.RUNNING,
            title="Extraction in progress",
            detail="Ingestion agent is extracting load order details from pasted email text.",
            activity_key="ingestion_started",
            load_order_id=None,
        )
        await session.commit()

        ingestion_result = await ingest_load_order_from_raw_text(
            session=session,
            user_id=user_id,
            raw_text=payload.source_email_text,
        )
        activity = await _log_delegation(
            session,
            load_order_id=ingestion_result.load_order.id,
            title="Delegated intake extraction completed",
            detail="Orchestrator routed pasted email text to intake extraction.",
            activity_key="delegated_intake_extraction",
            next_action="Review extracted draft",
            delegated_to="ingestion",
            action=payload.action,
        )

        await append_agent_activity(
            session,
            agent_kind=AgentKind.INGESTION,
            activity_state=AgentActivityState.COMPLETED,
            title="Extraction completed",
            detail="Ingestion agent finished extracting load order details.",
            activity_key="ingestion_completed",
            load_order_id=ingestion_result.load_order.id if ingestion_result.load_order else None,
        )

        if ingestion_result.load_order and ingestion_result.load_order.id:
            bool_settings = await load_boolean_settings(session)
            if bool_settings.get("enable_ingestion_smart_comms_handoff"):
                await _maybe_handoff_to_smart_comms(
                    session,
                    user_id=user_id,
                    order_id=ingestion_result.load_order.id,
                    missing_fields=ingestion_result.missing_fields,
                )

        return OrchestratorDelegationResponse(
            delegated_to="ingestion",
            activity=activity,
            ingestion_result=ingestion_result,
        )

    if payload.action == "draft_message":
        order = await _require_runtime_order(session, payload.load_order_id)
        conversation = await resolve_conversation(
            session,
            user_id=user_id,
            context_type=SmartCommsContextType.LOAD_ORDER,
            context_id=order.id,
            route_path=f"/orders/{order.id}",
            title=f"Order {order.id} message drafting",
        )
        activity = await _log_delegation(
            session,
            load_order_id=order.id,
            title="Delegated Smart Comms drafting opened",
            detail="Orchestrator routed operator drafting intent to Smart Comms.",
            activity_key="delegated_smart_comms_opened",
            next_action="Open Smart Comms conversation",
            delegated_to="smart_comms",
            action=payload.action,
        )
        return OrchestratorDelegationResponse(
            delegated_to="smart_comms",
            activity=activity,
            smart_comms_conversation=SmartCommsConversationResponse.model_validate(conversation),
        )

    if payload.action == "open_shipment_monitoring":
        order = await _require_runtime_order(session, payload.load_order_id)
        _require_formalized_for_monitoring(order)

        await append_agent_activity(
            session,
            agent_kind=AgentKind.MONITORING,
            activity_state=AgentActivityState.RUNNING,
            title="Shipment monitoring started",
            detail="Execution monitoring agent is generating route and shipment tracking data.",
            activity_key="monitoring_started",
            load_order_id=order.id,
        )
        await session.commit()

        await ensure_execution_monitoring_snapshot(
            session,
            order,
            source="delegated_orchestrator_monitoring_open",
        )
        monitoring_snapshot = await get_execution_monitoring_read_model(session, order.id)
        activity = await _log_delegation(
            session,
            load_order_id=order.id,
            title="Delegated shipment monitoring opened",
            detail="Orchestrator routed operator monitoring intent to the execution monitor.",
            activity_key="delegated_monitoring_opened",
            next_action="Review shipment progress",
            delegated_to="monitoring",
            action=payload.action,
        )

        await append_agent_activity(
            session,
            agent_kind=AgentKind.MONITORING,
            activity_state=AgentActivityState.COMPLETED,
            title="Shipment monitoring snapshot ready",
            detail="Geocoding, routing, and trip simulation completed.",
            activity_key="monitoring_completed",
            load_order_id=order.id,
        )

        return OrchestratorDelegationResponse(
            delegated_to="monitoring",
            activity=activity,
            monitoring_snapshot=monitoring_snapshot,
        )

    if payload.action == "run_carrier_search":
        order = await _require_runtime_order(session, payload.load_order_id)
        search_result, _ = await create_load_order_carrier_search(session, order.id)
        activity = await _log_delegation(
            session,
            load_order_id=order.id,
            title="Delegated carrier search completed",
            detail="Orchestrator routed operator carrier intent to carrier search.",
            activity_key="delegated_carrier_search_completed",
            next_action="Review ranked carriers",
            delegated_to="carrier_search",
            action=payload.action,
        )
        return OrchestratorDelegationResponse(
            delegated_to="carrier_search",
            activity=activity,
        )

    raise HTTPException(status_code=422, detail="Unsupported delegated action")


_HANDOFF_CRITICAL_FIELDS = frozenset({
    "customer_name",
    "origin_text",
    "destination_text",
    "origin_load_date",
    "cargo_description",
})


_HANDOFF_FIELD_LABELS = {
    "customer_name": "customer",
    "origin_text": "origin",
    "destination_text": "destination",
    "origin_load_date": "load date",
    "cargo_description": "cargo description",
}


def _format_handoff_field_list(fields: list[str]) -> str:
    labels = [_HANDOFF_FIELD_LABELS.get(field, field.replace("_", " ")) for field in fields]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


def _build_handoff_assistant_message(critical_missing: list[str]) -> str:
    field_list = _format_handoff_field_list(critical_missing)
    if len(critical_missing) == 1:
        noun = "field is"
        pronoun = "it"
    else:
        noun = "fields are"
        pronoun = "them"

    return (
        "I could not confidently complete the intake draft. "
        f"The highest-impact missing {noun} {field_list}. "
        f"Please ask the operator for clarification about {pronoun} before continuing."
    )


async def _maybe_handoff_to_smart_comms(
    session: AsyncSession,
    *,
    user_id: UUID,
    order_id: UUID,
    missing_fields: dict[str, str],
) -> None:
    critical_missing = [
        field for field in missing_fields if field in _HANDOFF_CRITICAL_FIELDS
    ]
    if not critical_missing:
        return

    assistant_message = _build_handoff_assistant_message(critical_missing)

    conversation = await resolve_conversation(
        session,
        user_id=user_id,
        context_type=SmartCommsContextType.LOAD_ORDER,
        context_id=order_id,
        route_path=f"/orders/{order_id}",
        title=f"Intake clarification for order",
    )

    await persist_assistant_message(
        session,
        conversation.id,
        assistant_message,
    )

    await append_agent_activity(
        session,
        agent_kind=AgentKind.ORCHESTRATOR,
        activity_state=AgentActivityState.AWAITING_OPERATOR,
        title="Ingestion completed with gaps — delegated clarification",
        detail=f"Missing critical fields: {', '.join(critical_missing)}. Smart Comms clarification prepared.",
        activity_key="ingestion_smart_comms_handoff",
        load_order_id=order_id,
        next_action="Review Smart Comms clarification",
    )

    await append_agent_activity(
        session,
        agent_kind=AgentKind.SMART_COMMS,
        activity_state=AgentActivityState.AWAITING_OPERATOR,
        title="Smart Comms clarification prepared",
        detail="Assistant message seeded with missing field guidance.",
        activity_key="smart_comms_clarification_prepared",
        load_order_id=order_id,
    )
