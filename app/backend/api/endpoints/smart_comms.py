"""API endpoints for Smart Comms conversations and streaming."""

import json

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.backend.api.dependencies.auth import CurrentUserDep, get_current_user
from app.backend.core.domain_enums import AgentActivityState, AgentKind, LoadOrderStatus
from app.backend.db.session import AsyncSessionDep
from app.backend.models.smart_comms_conversation import SmartCommsConversation
from app.backend.models.load_order import LoadOrder
from app.backend.schemas.agents import AgentStatusResponse, OrchestratorTimelineItem
from app.backend.schemas.load_order import DashboardLoadOrderSummaryResponse, LoadOrderListPageResponse
from app.backend.schemas.smart_comms import (
    SmartCommsConversationResponse,
    SmartCommsMessageRequest,
    SmartCommsMessageResponse,
    SmartCommsResolveRequest,
)
from app.backend.services.agent_activity_log import append_agent_activity, get_agent_statuses, get_orchestrator_timeline
from app.backend.services.load_order_human_validation import get_load_order_human_validation_context
from app.backend.services.load_orders import get_dashboard_load_order_summary, list_load_orders_page
from app.backend.services.smart_comms_service import (
    delete_conversation,
    get_conversation_messages,
    get_conversation_or_404_for_user,
    persist_assistant_message,
    persist_user_message,
    resolve_conversation,
)
from app.backend.services.smart_comms_runtime import stream_chat_response, get_local_agent_provenance
from app.backend.services.runtime_settings import get_runtime_settings, load_boolean_settings
from app.backend.services.rag_memory import (
    retrieve_smart_comms_context,
    index_smart_comms_memory,
)

_CONTEXT_SYSTEM_PROMPTS: dict[str, str] = {
    "dashboard": (
        "You are viewing the Hermes operations dashboard. The operator can see agent status cards, "
        "an orchestrator activity timeline, and monitoring alerts. Help them understand the current "
        "state of the workflow, explain what agents are doing, and suggest next actions."
    ),
    "orders_list": (
        "You are viewing the orders list. Help the operator understand order statuses, "
        "filter priorities, and identify which orders need attention."
    ),
    "load_order": (
        "You are viewing a specific load order. Help the operator understand its current status, "
        "what happened so far, and what the next step is in the workflow."
    ),
    "carrier_match": (
        "You are viewing the carrier match page for an order. The operator is comparing carrier "
        "proposals ranked by an intelligent scoring algorithm. Help them understand ranking scores, "
        "score breakdowns (route match, price competitiveness, reliability), and agent reasoning. "
        "Explain why certain carriers are ranked higher or rejected."
    ),
    "intake_review": (
        "You are viewing the intake review page. The operator is reviewing data extracted by the "
        "ingestion agent from unstructured text. Help them understand what was extracted, what's "
        "missing, and whether the order looks viable."
    ),
    "settings": (
        "You are viewing the settings page. The operator is configuring agent behavior toggles "
        "and checking runtime status. Help them understand what each setting controls and the "
        "current state of AI providers and ChromaDB connectivity."
    ),
}


def _build_system_prompt(context_type: str, context_data: str | None = None) -> str:
    context_description = _CONTEXT_SYSTEM_PROMPTS.get(
        context_type,
        "Help the operator with the Hermes freight forwarding platform.",
    )
    prompt = (
        "You are Smart Comms, the AI assistant inside Hermes — a multi-agent freight forwarding "
        "automation platform. You are concise, operationally credible, and helpful. "
        "You answer questions about orders, carriers, routes, workflow status, and operator actions. "
        "Use only the provided page data and persisted conversation context. "
        "If the answer is not supported by the provided data, say so plainly instead of guessing. "
        "When asked to count items or list statuses, derive the answer strictly from the provided records. "
        "Do not invent orders, totals, incidents, settings values, or timeline events. "
        "Use markdown formatting. Keep responses short, concrete, and action-oriented.\n\n"
        f"Current page context: {context_type}.\n"
        f"{context_description}"
    )
    if context_data:
        prompt += f"\n\nHere is the current data for this page:\n{context_data}"
    return prompt


async def _load_context_data(
    session: AsyncSession,
    context_type: str,
    context_id: str | None,
) -> str | None:
    """Load relevant domain data for the current page context."""
    if context_type == "settings":
        settings = await get_runtime_settings(session)
        return (
            "Runtime settings:\n"
            f"- Auto carrier search: {settings.enable_auto_carrier_search}\n"
            f"- Ingestion to Smart Comms handoff: {settings.enable_ingestion_smart_comms_handoff}\n"
            f"- Smart Comms retrieval: {settings.enable_smart_comms_retrieval}\n"
            f"- Carrier search retrieval: {settings.enable_carrier_search_retrieval}\n"
            f"- Ingestion AI: {settings.ingestion_provider or 'unknown'} / {settings.ingestion_model_name or 'not configured'}\n"
            f"- Reasoning AI: {settings.reasoning_provider or 'unknown'} / {settings.reasoning_model_name or 'not configured'}\n"
            f"- Local Chroma runtime available: {settings.chroma_reachable}"
        )

    if context_type == "dashboard":
        summary = await get_dashboard_load_order_summary(session, limit=5)
        agent_statuses = await get_agent_statuses(session)
        timeline = await get_orchestrator_timeline(session, limit=8)
        return _format_dashboard_context(summary, agent_statuses, timeline)

    if context_type == "orders_list":
        orders_page = await list_load_orders_page(session, active_only=False, skip=0, limit=20)
        return _format_orders_list_context(orders_page)

    if context_id is None:
        return None

    order_id = UUID(context_id)

    if context_type == "load_order":
        order = await session.get(LoadOrder, order_id)
        if order is None:
            return None
        return (
            f"Order {order.id}:\n"
            f"- Status: {order.status}\n"
            f"- Customer: {order.customer_name or 'TBD'}\n"
            f"- Route: {order.origin_text or 'TBD'} -> {order.destination_text or 'TBD'}\n"
            f"- Cargo: {order.cargo_description or 'TBD'}\n"
            f"- Weight: {order.weight_kg or 'TBD'} kg\n"
            f"- Customer price: {order.customer_price or 'TBD'} {order.currency}\n"
            f"- ADR required: {order.adr_required}"
        )

    if context_type == "carrier_match":
        from app.backend.models.trip import Trip

        order = await session.get(LoadOrder, order_id)
        if order is None:
            return None

        stmt = (
            select(Trip)
            .options(selectinload(Trip.carrier))
            .where(Trip.load_order_id == order_id)
            .order_by(Trip.ranking_score.desc().nullslast())
            .limit(10)
        )
        result = await session.execute(stmt)
        trips = list(result.scalars().all())

        lines = [
            f"Order: {order.origin_text or 'TBD'} -> {order.destination_text or 'TBD'}",
            f"Customer price: {order.customer_price or 'TBD'} {order.currency}",
            f"Status: {order.status}",
            "",
            "Top carrier candidates (by ranking score):",
        ]
        for i, trip in enumerate(trips, 1):
            carrier_name = trip.carrier.company_name if trip.carrier else "Unknown"
            lines.append(
                f"{i}. {carrier_name} — score: {trip.ranking_score or 'N/A'}, "
                f"price: {trip.carrier_price or 'N/A'}, margin: {trip.profit_margin or 'N/A'}, "
                f"status: {trip.proposal_status}"
            )
            if trip.agent_reasoning:
                lines.append(f"   Reasoning: {trip.agent_reasoning}")

        return "\n".join(lines)

    if context_type == "intake_review":
        context = await get_load_order_human_validation_context(session, order_id)
        missing = list(context.missing_fields.keys())
        blocked = list(context.blocked_missing_fields.keys())
        return (
            f"Order {context.load_order.id}:\n"
            f"- Status: {context.load_order.status}\n"
            f"- Customer: {context.load_order.customer_name or 'TBD'}\n"
            f"- Route: {context.load_order.origin_text or 'TBD'} -> {context.load_order.destination_text or 'TBD'}\n"
            f"- Cargo: {context.load_order.cargo_description or 'TBD'}\n"
            f"- Missing fields: {', '.join(missing) if missing else 'none'}\n"
            f"- Blocked missing fields: {', '.join(blocked) if blocked else 'none'}\n"
            f"- Can confirm viability: {context.can_confirm_viability}\n"
            f"- Latest ingestion path: {context.latest_ingestion_run.execution_path or 'unknown'}\n"
            f"- Latest ingestion provider/model: {(context.latest_ingestion_run.provider or 'unknown')} / {(context.latest_ingestion_run.model_name or 'unknown')}"
        )

    return None


def _format_dashboard_context(
    summary: DashboardLoadOrderSummaryResponse,
    agent_statuses: list[AgentStatusResponse],
    timeline: list[OrchestratorTimelineItem],
) -> str:
    lines = [
        "Dashboard snapshot:",
        f"- Active orders: {summary.active_order_count}",
        f"- Orders needing attention: {summary.needs_attention_count}",
        "",
        "Attention orders:",
    ]
    for order in summary.attention_orders:
        lines.append(
            f"- {order.id}: {order.customer_name or 'Unknown'} | {order.status} | {order.origin_text or 'TBD'} -> {order.destination_text or 'TBD'}"
        )

    lines.extend(["", "Recent active orders:"])
    for order in summary.recent_active_orders:
        lines.append(
            f"- {order.id}: {order.customer_name or 'Unknown'} | {order.status} | {order.origin_text or 'TBD'} -> {order.destination_text or 'TBD'}"
        )

    lines.extend(["", "Agent status cards:"])
    for status in agent_statuses:
        lines.append(
            f"- {status.display_name}: state={status.state}, headline={status.headline}, active_items={status.active_item_count}"
        )

    lines.extend(["", "Recent timeline events:"])
    for item in timeline:
        lines.append(
            f"- {item.created_at.isoformat()}: {item.agent} | {item.title} | order={item.load_order_id or 'none'} | status={item.order_status or 'n/a'}"
        )

    return "\n".join(lines)


def _format_orders_list_context(orders_page: LoadOrderListPageResponse) -> str:
    status_counts: dict[str, int] = {}
    for order in orders_page.items:
        key = order.status.value if isinstance(order.status, LoadOrderStatus) else str(order.status)
        status_counts[key] = status_counts.get(key, 0) + 1

    lines = [
        "Orders list snapshot:",
        f"- Total loaded items: {len(orders_page.items)}",
        f"- Page total count: {orders_page.total}",
        f"- Page window: skip={orders_page.skip}, limit={orders_page.limit}",
        "",
        "Status counts in loaded items:",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")

    lines.extend(["", "Loaded orders:"])
    for order in orders_page.items:
        lines.append(
            f"- {order.id}: {order.customer_name or 'Unknown'} | {order.status} | {order.origin_text or 'TBD'} -> {order.destination_text or 'TBD'} | updated_at={order.updated_at.isoformat()}"
        )

    return "\n".join(lines)

async def _get_provenance_metadata() -> dict[str, object]:
    """Gather runtime provenance metadata for persistence."""
    return get_local_agent_provenance()


router = APIRouter(
    prefix="/smart-comms",
    tags=["Smart Comms"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/conversations/resolve", response_model=SmartCommsConversationResponse)
async def resolve_conversation_endpoint(
    payload: SmartCommsResolveRequest,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
) -> SmartCommsConversationResponse:
    """Resolve or create a conversation for the current page context."""
    conversation = await resolve_conversation(
        session,
        user_id=current_user.id,
        context_type=payload.context_type,
        context_id=payload.context_id,
        route_path=payload.route_path,
    )
    await session.commit()
    return SmartCommsConversationResponse.model_validate(conversation)


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message_endpoint(
    conversation_id: UUID,
    payload: SmartCommsMessageRequest,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
) -> StreamingResponse:
    """Stream an assistant response for one user message."""
    conversation = await get_conversation_or_404_for_user(
        session, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await persist_user_message(session, conversation_id, payload.content)
    await append_agent_activity(
        session,
        agent_kind=AgentKind.SMART_COMMS,
        activity_state=AgentActivityState.RUNNING,
        title="Assistant reply in progress",
        detail="Smart Comms is generating an assistant response.",
        activity_key="assistant_reply_started",
        load_order_id=conversation.context_id,
    )
    await session.commit()

    context_type = conversation.context_type.value
    context_id = str(conversation.context_id) if conversation.context_id else None

    context_data = await _load_context_data(session, context_type, context_id)
    order: LoadOrder | None = None
    if context_type == "load_order" and context_id:
        order = await session.get(LoadOrder, UUID(context_id))

    bool_settings = await load_boolean_settings(session)
    retrieval_block = ""
    if bool_settings.get("enable_smart_comms_retrieval") and context_type == "load_order" and context_id:
        try:
            if order:
                query = f"{order.origin_text or ''} {order.destination_text or ''} {order.cargo_description or ''} {order.customer_name or ''}"
                snippets = retrieve_smart_comms_context(query, top_k=3)
                if snippets:
                    retrieval_block = "Retrieved memory (similar past interactions):\n"
                    for s in snippets:
                        retrieval_block += f"- {s['document']}\n"
        except Exception:
            pass

    messages = await get_conversation_messages(session, conversation_id)
    system_prompt = _build_system_prompt(context_type, context_data)
    if retrieval_block:
        system_prompt += f"\n\n{retrieval_block}"
    chat_messages = [{"role": "system", "content": system_prompt}]
    chat_messages.extend(
        {"role": "user" if m.role == "user" else "assistant", "content": m.content}
        for m in messages
    )

    async def event_stream():
        full_response = ""
        yield f"event: conversation\ndata: {json.dumps({'conversation_id': str(conversation_id)})}\n\n"

        try:
            async for chunk in stream_chat_response(chat_messages):
                full_response += chunk
                yield f"event: delta\ndata: {json.dumps({'chunk': chunk})}\n\n"

            assistant_msg = await persist_assistant_message(
                session,
                conversation_id,
                full_response,
                extra_metadata=(
                    await _get_provenance_metadata()
                ),
            )

            if context_type == "load_order" and context_id and order:
                try:
                    route_label = f"{order.origin_text or '?'} -> {order.destination_text or '?'}"
                    index_smart_comms_memory(
                        order_id=str(order.id),
                        customer_name=order.customer_name or "Unknown",
                        route_label=route_label,
                        operator_question=payload.content,
                        assistant_response=full_response,
                    )
                except Exception:
                    pass

            await append_agent_activity(
                session,
                agent_kind=AgentKind.SMART_COMMS,
                activity_state=AgentActivityState.COMPLETED,
                title="Assistant reply completed",
                detail="Smart Comms generated an assistant response.",
                activity_key="assistant_reply_completed",
                load_order_id=conversation.context_id,
            )
            await session.commit()

            yield f"event: done\ndata: {json.dumps({'conversation_id': str(conversation_id), 'message_id': str(assistant_msg.id)})}\n\n"
        except Exception as e:
            await append_agent_activity(
                session,
                agent_kind=AgentKind.SMART_COMMS,
                activity_state=AgentActivityState.ERROR,
                title="Assistant reply failed",
                detail=f"Smart Comms failed to generate a response: {e}",
                activity_key="assistant_reply_failed",
                load_order_id=conversation.context_id,
            )
            await session.commit()
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[SmartCommsMessageResponse])
async def get_conversation_messages_endpoint(
    conversation_id: UUID,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
) -> list[SmartCommsMessageResponse]:
    """Return persisted message history for a conversation owned by the current user."""
    conversation = await get_conversation_or_404_for_user(
        session, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    messages = await get_conversation_messages(session, conversation_id)
    return [SmartCommsMessageResponse.model_validate(m) for m in messages]


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_endpoint(
    conversation_id: UUID,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
) -> Response:
    """Delete a conversation and all its messages."""
    await delete_conversation(session, conversation_id, current_user.id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
