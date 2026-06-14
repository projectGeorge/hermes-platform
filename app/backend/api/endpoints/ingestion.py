from fastapi import APIRouter, Depends, HTTPException, status

from app.backend.api.dependencies.auth import CurrentUserDep, get_current_user
from app.backend.core.domain_enums import AgentActivityState, AgentKind
from app.backend.db.session import AsyncSessionDep
from app.backend.services.delegated_orchestrator import _maybe_handoff_to_smart_comms
from app.backend.schemas.ingestion import (
    IngestionLoadOrderRequestBrowser,
    LoadOrderIngestionResponse,
)
from app.backend.services.agent_activity_log import append_agent_activity
from app.backend.services.load_order_ingestion import ingest_load_order_from_raw_text
from app.backend.services.load_order_orchestrator import log_ingestion_agent_completed
from app.backend.services.runtime_settings import load_boolean_settings

router = APIRouter(
    prefix="/ingestion",
    tags=["Ingestion"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/load-orders",
    response_model=LoadOrderIngestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_load_order(
    payload: IngestionLoadOrderRequestBrowser,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
) -> LoadOrderIngestionResponse:
    await append_agent_activity(
        session,
        agent_kind=AgentKind.INGESTION,
        activity_state=AgentActivityState.RUNNING,
        title="Extraction in progress",
        detail="Ingestion agent is extracting load order details from raw email text.",
        activity_key="ingestion_started",
        load_order_id=None,
    )
    await session.commit()

    try:
        response = await ingest_load_order_from_raw_text(
            session=session,
            user_id=current_user.id,
            raw_text=payload.raw_text,
        )
    except HTTPException:
        await session.commit()
        raise

    if response.load_order is not None:
        from app.backend.models.load_order import LoadOrder
        order = await session.get(LoadOrder, response.load_order.id)
        if order is not None:
            await log_ingestion_agent_completed(session, order)

            bool_settings = await load_boolean_settings(session)
            if bool_settings.get("enable_ingestion_smart_comms_handoff"):
                await _maybe_handoff_to_smart_comms(
                    session,
                    user_id=current_user.id,
                    order_id=order.id,
                    missing_fields=response.missing_fields,
                )

    await session.commit()
    return response
