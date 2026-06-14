from enum import StrEnum


class IngestionRunStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class LoadOrderHumanReviewStatus(StrEnum):
    FIELDS_UPDATED = "fields_updated"
    VIABILITY_CONFIRMED = "viability_confirmed"


class TripProposalStatus(StrEnum):
    CANDIDATE = "candidate"
    REJECTED = "rejected"


class CarrierRejectionReason(StrEnum):
    INVALID_DOCUMENTATION = "invalid_documentation"
    ADR_NOT_SUPPORTED = "adr_not_supported"
    TRUCK_TYPE_MISMATCH = "truck_type_mismatch"
    NON_PROFITABLE = "non_profitable"


LOAD_ORDER_INGESTION_ROUTE = "load_order_ingestion"


class AgentKind(StrEnum):
    ORCHESTRATOR = "orchestrator"
    INGESTION = "ingestion"
    CARRIER_SEARCH = "carrier_search"
    SMART_COMMS = "smart_comms"
    MONITORING = "monitoring"


class AgentActivityState(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    AWAITING_OPERATOR = "awaiting_operator"
    WARNING = "warning"
    ERROR = "error"


class MonitoringAlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MonitoringAlertType(StrEnum):
    STATUS_CHANGED = "status_changed"
    DEADLINE_APPROACHING = "deadline_approaching"
    MISSING_ROUTE_DATA = "missing_route_data"
    STALLED_WORKFLOW = "stalled_workflow"
    MARGIN_RISK = "margin_risk"


class MonitoringAlertStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class ExecutionMonitoringStatus(StrEnum):
    PLANNED = "planned"
    IN_TRANSIT = "in_transit"
    DELAYED = "delayed"
    DELIVERED = "delivered"


class SmartCommsContextType(StrEnum):
    DASHBOARD = "dashboard"
    ORDERS_LIST = "orders_list"
    LOAD_ORDER = "load_order"
    CARRIER_MATCH = "carrier_match"
    INTAKE_REVIEW = "intake_review"
    SETTINGS = "settings"


class SmartCommsMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class CarrierPricingModel(StrEnum):
    PER_KM = "per_km"
    FLAT_RATE = "flat_rate"
    MARKET_ADJUSTED = "market_adjusted"


class LoadOrderStatus(StrEnum):
    PENDING_INGESTION = "pending_ingestion"
    VIABILITY_PENDING = "viability_pending"
    VIABILITY_CONFIRMED = "viability_confirmed"
    SEARCHING_CARRIER = "searching_carrier"
    READY_FOR_FORMALIZATION = "ready_for_formalization"
    FORMALIZED = "formalized"
    CANCELLED = "cancelled"


LOAD_ORDER_TRANSITIONS: dict[LoadOrderStatus, set[LoadOrderStatus]] = {
    LoadOrderStatus.PENDING_INGESTION: {
        LoadOrderStatus.VIABILITY_PENDING,
        LoadOrderStatus.CANCELLED,
    },
    LoadOrderStatus.VIABILITY_PENDING: {
        LoadOrderStatus.VIABILITY_CONFIRMED,
        LoadOrderStatus.CANCELLED,
    },
    LoadOrderStatus.VIABILITY_CONFIRMED: {
        LoadOrderStatus.SEARCHING_CARRIER,
        LoadOrderStatus.CANCELLED,
    },
    LoadOrderStatus.SEARCHING_CARRIER: {
        LoadOrderStatus.READY_FOR_FORMALIZATION,
        LoadOrderStatus.CANCELLED,
    },
    LoadOrderStatus.READY_FOR_FORMALIZATION: {
        LoadOrderStatus.FORMALIZED,
        LoadOrderStatus.CANCELLED,
    },
    LoadOrderStatus.FORMALIZED: {
        LoadOrderStatus.CANCELLED,
    },
    LoadOrderStatus.CANCELLED: set(),
}


def validate_load_order_transition(current: LoadOrderStatus, new: LoadOrderStatus) -> None:
    if new not in LOAD_ORDER_TRANSITIONS[current]:
        raise ValueError(f"Transition not allowed: {current} -> {new}")
