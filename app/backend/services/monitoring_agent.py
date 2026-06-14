"""Monitoring agent rule engine for operational alerts."""

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.domain_enums import (
    LoadOrderStatus,
    MonitoringAlertSeverity,
    MonitoringAlertStatus,
    MonitoringAlertType,
    TripProposalStatus,
)
from app.backend.core.settings import Settings
from app.backend.models.load_order import LoadOrder
from app.backend.models.monitoring_alert import MonitoringAlert
from app.backend.models.trip import Trip


class ModelMonitoringAlert(BaseModel):
    should_open: bool = False
    alert_type: str = ""
    severity: str = "info"
    title: str = ""
    detail: str = ""
    suggested_action: str | None = None

    model_config = {"extra": "forbid"}


_VALID_ALERT_TYPES = frozenset({
    "status_changed", "deadline_approaching", "missing_route_data",
    "stalled_workflow", "margin_risk",
})

_VALID_SEVERITIES = frozenset({"info", "warning", "critical"})

_FALLBACK_MONITORING_ALERT = ModelMonitoringAlert(
    should_open=False,
    alert_type="",
    severity="info",
    title="Monitoring fallback",
    detail="Fallback: cloud evaluation unavailable or returned invalid output.",
    suggested_action=None,
)


def _validate_monitoring_alert(raw: dict) -> ModelMonitoringAlert:
    return _try_validate_monitoring_alert(raw)[0]


def _try_validate_monitoring_alert(raw: dict) -> tuple[ModelMonitoringAlert, bool]:
    try:
        alert = ModelMonitoringAlert(**raw)
    except Exception:
        return _FALLBACK_MONITORING_ALERT, False

    if alert.alert_type and alert.alert_type not in _VALID_ALERT_TYPES:
        return _FALLBACK_MONITORING_ALERT, False

    if alert.severity not in _VALID_SEVERITIES:
        return _FALLBACK_MONITORING_ALERT, False

    return alert, True


async def _generate_cloud_alert_result(
    *,
    settings: Settings,
    order_summary: str,
) -> tuple[ModelMonitoringAlert, bool, str | None]:
    from app.backend.services.model_runtime_gateway import structured_completion

    try:
        result = await structured_completion(
            settings=settings,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a freight operations monitoring agent. Given an order summary, "
                        "evaluate whether an alert should be opened. Return valid JSON with keys: "
                        "should_open (boolean), alert_type (string: status_changed, deadline_approaching, "
                        "missing_route_data, stalled_workflow, margin_risk), severity (string: info, "
                        "warning, critical), title (string), detail (string), suggested_action (string or null). "
                        "Be conservative — only open alerts when there is a clear operational concern. "
                        "Do not invent events, route changes, or commercial facts that are not present in the summary."
                    ),
                },
                {
                    "role": "user",
                    "content": order_summary,
                },
            ],
            profile="reasoning",
        )
    except Exception:
        return _FALLBACK_MONITORING_ALERT, False, "runtime_error"

    alert, is_valid = _try_validate_monitoring_alert(result.content)
    return alert, is_valid, None if is_valid else "invalid_output"


async def _generate_cloud_alert(
    *,
    settings: Settings,
    order_summary: str,
) -> ModelMonitoringAlert:
    alert, _, _ = await _generate_cloud_alert_result(
        settings=settings,
        order_summary=order_summary,
    )
    return alert

_STALLED_THRESHOLD_HOURS = 24
_DEADLINE_THRESHOLD_HOURS = 24
_MARGIN_RISK_THRESHOLD_RATIO = 0.10

_STALLED_STATUSES = {
    LoadOrderStatus.PENDING_INGESTION,
    LoadOrderStatus.VIABILITY_PENDING,
    LoadOrderStatus.SEARCHING_CARRIER,
}

_MARGIN_RELEVANT_STATUSES = {
    LoadOrderStatus.VIABILITY_CONFIRMED,
    LoadOrderStatus.SEARCHING_CARRIER,
    LoadOrderStatus.READY_FOR_FORMALIZATION,
}


async def _upsert_alert(
    session: AsyncSession,
    *,
    load_order_id: UUID | None,
    alert_type: MonitoringAlertType,
    severity: MonitoringAlertSeverity,
    title: str,
    detail: str | None,
    dedupe_key: str,
    extra_metadata: dict[str, object] | None = None,
) -> MonitoringAlert:
    """Create or reopen an alert, deduplicating on dedupe_key for open alerts."""
    stmt = select(MonitoringAlert).where(
        MonitoringAlert.dedupe_key == dedupe_key,
        MonitoringAlert.status == MonitoringAlertStatus.OPEN,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        return existing

    alert = MonitoringAlert(
        load_order_id=load_order_id,
        alert_type=alert_type,
        severity=severity,
        status=MonitoringAlertStatus.OPEN,
        title=title,
        detail=detail,
        dedupe_key=dedupe_key,
        extra_metadata=extra_metadata,
    )
    session.add(alert)
    await session.flush()
    return alert


async def _resolve_alerts_for_dedupe_prefix(
    session: AsyncSession,
    load_order_id: UUID,
    alert_type: MonitoringAlertType,
) -> None:
    """Resolve open alerts for a given order and type when condition disappears."""
    stmt = select(MonitoringAlert).where(
        MonitoringAlert.load_order_id == load_order_id,
        MonitoringAlert.alert_type == alert_type,
        MonitoringAlert.status == MonitoringAlertStatus.OPEN,
    )
    result = await session.execute(stmt)
    for alert in result.scalars().all():
        alert.status = MonitoringAlertStatus.RESOLVED
        alert.resolved_at = datetime.now()


async def _resolve_open_alerts_for_order(
    session: AsyncSession,
    load_order_id: UUID,
) -> None:
    stmt = select(MonitoringAlert).where(
        MonitoringAlert.load_order_id == load_order_id,
        MonitoringAlert.status == MonitoringAlertStatus.OPEN,
    )
    result = await session.execute(stmt)
    for alert in result.scalars().all():
        alert.status = MonitoringAlertStatus.RESOLVED
        alert.resolved_at = datetime.now()


async def _get_order_margin(session: AsyncSession, order: LoadOrder) -> float | None:
    """Get the effective margin for margin_risk evaluation.

    Uses the selected trip's margin if available, otherwise the best candidate margin.
    """
    from decimal import Decimal

    stmt = select(Trip).where(Trip.load_order_id == order.id)
    result = await session.execute(stmt)
    trips = list(result.scalars().all())

    if not trips:
        return None

    selected = next((t for t in trips if t.id == order.selected_trip_id), None)
    if selected and selected.profit_margin is not None:
        return float(selected.profit_margin)

    candidates = [
        t for t in trips
        if t.proposal_status == TripProposalStatus.CANDIDATE.value
        and t.profit_margin is not None
    ]
    if not candidates:
        return None

    best = max(candidates, key=lambda t: float(t.profit_margin))
    return float(best.profit_margin)


async def _evaluate_cloud_alerts(
    session: AsyncSession,
    order: LoadOrder,
    now: datetime,
    created: list[MonitoringAlert],
) -> bool:
    from app.backend.core.settings import get_settings

    settings = get_settings()
    if not settings.reasoning_model_name:
        return False

    hours_since_created = (now - order.created_at).total_seconds() / 3600 if order.created_at else 0
    hours_until_deadline = (
        (order.origin_load_date - now).total_seconds() / 3600
        if order.origin_load_date else 0
    )
    current_margin = await _get_order_margin(session, order)

    summary_parts = [
        f"Order status: {order.status.value}",
        f"Customer: {order.customer_name or 'unknown'}",
        f"Route: {order.origin_text or 'missing'} -> {order.destination_text or 'missing'}",
        f"ADR required: {order.adr_required}",
        f"Hours since created: {int(hours_since_created)}",
    ]
    if order.origin_load_date:
        summary_parts.append(f"Hours until deadline: {int(hours_until_deadline)}")
    if order.customer_price:
        summary_parts.append(f"Customer price: {order.customer_price}")
    if current_margin is not None:
        summary_parts.append(f"Current best margin: {current_margin:.2f}")

    alert, is_valid, failure_reason = await _generate_cloud_alert_result(
        settings=settings,
        order_summary="\n".join(summary_parts),
    )

    await _resolve_open_alerts_for_order(session, order.id)

    if is_valid:
        if alert.should_open and alert.alert_type:
            try:
                dedupe_key = f"cloud:{alert.alert_type}:{order.id}"
                persisted = await _upsert_alert(
                    session,
                    load_order_id=order.id,
                    alert_type=MonitoringAlertType(alert.alert_type),
                    severity=MonitoringAlertSeverity(alert.severity),
                    title=alert.title,
                    detail=alert.detail,
                    dedupe_key=dedupe_key,
                    extra_metadata={
                        "provider": settings.reasoning_model_provider,
                        "model_name": settings.reasoning_model_name,
                        "runtime_profile": "reasoning",
                        "execution_path": "cloud",
                        "suggested_action": alert.suggested_action,
                    },
                )
                created.append(persisted)
            except (ValueError, KeyError):
                return False
        return True

    fallback_metadata = {
        "provider": settings.reasoning_model_provider,
        "model_name": settings.reasoning_model_name,
        "runtime_profile": "reasoning",
        "execution_path": "fallback",
        "fallback_reason": failure_reason or "invalid_output",
    }
    created.extend(
        await _evaluate_deterministic_alerts(
            session,
            order,
            now,
            extra_metadata=fallback_metadata,
            dedupe_prefix="fallback",
        )
    )
    return True


def _with_prefix(dedupe_key: str, prefix: str | None) -> str:
    if not prefix:
        return dedupe_key
    return f"{prefix}:{dedupe_key}"


async def _evaluate_deterministic_alerts(
    session: AsyncSession,
    order: LoadOrder,
    now: datetime,
    *,
    extra_metadata: dict[str, object] | None = None,
    dedupe_prefix: str | None = None,
) -> list[MonitoringAlert]:
    created: list[MonitoringAlert] = []

    # Rule 1: missing_route_data
    if order.status in {
        LoadOrderStatus.VIABILITY_CONFIRMED,
        LoadOrderStatus.SEARCHING_CARRIER,
        LoadOrderStatus.READY_FOR_FORMALIZATION,
    }:
        if not order.origin_text or not order.destination_text:
            dedupe_key = _with_prefix(f"missing_route_data:{order.id}", dedupe_prefix)
            alert = await _upsert_alert(
                session,
                load_order_id=order.id,
                alert_type=MonitoringAlertType.MISSING_ROUTE_DATA,
                severity=MonitoringAlertSeverity.WARNING,
                title="Missing route data",
                detail="Order is missing origin or destination text needed for downstream work.",
                dedupe_key=dedupe_key,
                extra_metadata=extra_metadata,
            )
            created.append(alert)
        else:
            await _resolve_alerts_for_dedupe_prefix(
                session, order.id, MonitoringAlertType.MISSING_ROUTE_DATA
            )

    # Rule 2: deadline_approaching
    deadline_triggered = False
    if (
        order.origin_load_date is not None
        and order.status != LoadOrderStatus.READY_FOR_FORMALIZATION
        and order.status != LoadOrderStatus.CANCELLED
    ):
        hours_until_deadline = (order.origin_load_date - now).total_seconds() / 3600
        if 0 < hours_until_deadline <= _DEADLINE_THRESHOLD_HOURS:
            deadline_triggered = True
            dedupe_key = _with_prefix(f"deadline_approaching:{order.id}", dedupe_prefix)
            alert = await _upsert_alert(
                session,
                load_order_id=order.id,
                alert_type=MonitoringAlertType.DEADLINE_APPROACHING,
                severity=MonitoringAlertSeverity.WARNING,
                title="Pickup deadline approaching",
                detail=f"Pickup deadline in {int(hours_until_deadline)}h. Order not yet ready for formalization.",
                dedupe_key=dedupe_key,
                extra_metadata=extra_metadata,
            )
            created.append(alert)

    if not deadline_triggered:
        await _resolve_alerts_for_dedupe_prefix(
            session, order.id, MonitoringAlertType.DEADLINE_APPROACHING
        )

    # Rule 3: stalled_workflow
    stalled_triggered = False
    if order.status in _STALLED_STATUSES and order.created_at is not None:
        hours_since_created = (now - order.created_at).total_seconds() / 3600
        if hours_since_created > _STALLED_THRESHOLD_HOURS:
            stalled_triggered = True
            dedupe_key = _with_prefix(
                f"stalled_workflow:{order.id}:{order.status.value}",
                dedupe_prefix,
            )
            alert = await _upsert_alert(
                session,
                load_order_id=order.id,
                alert_type=MonitoringAlertType.STALLED_WORKFLOW,
                severity=MonitoringAlertSeverity.WARNING,
                title=f"Workflow stalled in {order.status.value}",
                detail=f"Order has been in {order.status.value} for {int(hours_since_created)}h.",
                dedupe_key=dedupe_key,
                extra_metadata=extra_metadata,
            )
            created.append(alert)

    if not stalled_triggered:
        await _resolve_alerts_for_dedupe_prefix(
            session, order.id, MonitoringAlertType.STALLED_WORKFLOW
        )

    # Rule 4: margin_risk
    margin_triggered = False
    if (
        order.status in _MARGIN_RELEVANT_STATUSES
        and order.customer_price is not None
        and float(order.customer_price) > 0
    ):
        margin = await _get_order_margin(session, order)
        if margin is not None:
            threshold = float(order.customer_price) * _MARGIN_RISK_THRESHOLD_RATIO
            if margin < threshold:
                margin_triggered = True
                dedupe_key = _with_prefix(f"margin_risk:{order.id}", dedupe_prefix)
                alert = await _upsert_alert(
                    session,
                    load_order_id=order.id,
                    alert_type=MonitoringAlertType.MARGIN_RISK,
                    severity=MonitoringAlertSeverity.WARNING,
                    title="Margin below risk threshold",
                    detail=f"Best margin ({margin:.2f}) is below 10% of customer price ({float(order.customer_price):.2f}).",
                    dedupe_key=dedupe_key,
                    extra_metadata=extra_metadata,
                )
                created.append(alert)

    if not margin_triggered:
        await _resolve_alerts_for_dedupe_prefix(
            session, order.id, MonitoringAlertType.MARGIN_RISK
        )

    # Rule 5: status_changed (informational)
    dedupe_key = _with_prefix(f"status_changed:{order.id}:{order.status.value}", dedupe_prefix)
    alert = await _upsert_alert(
        session,
        load_order_id=order.id,
        alert_type=MonitoringAlertType.STATUS_CHANGED,
        severity=MonitoringAlertSeverity.INFO,
        title=f"Status changed to {order.status.value}",
        detail=f"Order transitioned to {order.status.value}.",
        dedupe_key=dedupe_key,
        extra_metadata=extra_metadata,
    )
    created.append(alert)

    return created


async def evaluate_order_alerts(
    session: AsyncSession,
    order: LoadOrder,
    *,
    allow_cloud_reasoning: bool = False,
) -> list[MonitoringAlert]:
    """Evaluate monitoring rules for a single order.

    Cloud reasoning is opt-in so routine write paths and read models stay cost-bounded.
    """
    now = datetime.now()

    created: list[MonitoringAlert] = []
    if allow_cloud_reasoning and await _evaluate_cloud_alerts(session, order, now, created):
        return created

    return await _evaluate_deterministic_alerts(session, order, now)


async def refresh_active_orders_alerts(
    session: AsyncSession,
) -> None:
    """Re-evaluate monitoring for all non-cancelled orders."""
    stmt = select(LoadOrder).where(
        LoadOrder.status != LoadOrderStatus.CANCELLED,
    )
    result = await session.execute(stmt)
    for order in result.scalars().all():
        await evaluate_order_alerts(session, order)


async def get_open_alerts(
    session: AsyncSession,
    *,
    limit: int = 50,
    refresh: bool = False,
) -> list[MonitoringAlert]:
    """Return recent open monitoring alerts, optionally refreshing first."""
    if refresh:
        await refresh_active_orders_alerts(session)

    stmt = (
        select(MonitoringAlert)
        .where(MonitoringAlert.status == MonitoringAlertStatus.OPEN)
        .order_by(MonitoringAlert.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
