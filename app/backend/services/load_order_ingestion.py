"""Deterministic and model-backed load order ingestion service."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any, NotRequired, TypedDict
import unicodedata
from uuid import UUID

from fastapi import HTTPException
from langgraph.graph import END, StateGraph
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.domain_enums import (
    IngestionRunStatus,
    LOAD_ORDER_INGESTION_ROUTE,
    LoadOrderStatus,
)
from app.backend.core.settings import get_settings
from app.backend.models.ingestion_run import IngestionRun
from app.backend.models.user import User
from app.backend.schemas.ingestion import LoadOrderIngestionResponse
from app.backend.schemas.load_order import LoadOrderCreate, LoadOrderResponse
from app.backend.services.ingestion_model_runtime import (
    ModelExtractionError,
    extract_load_order_with_model,
)
from app.backend.services.load_orders import create_load_order
from app.backend.services.prototype_catalog import PROTOTYPE_TRUCK_TYPES

_TRACKED_FIELDS: tuple[str, ...] = (
    "customer_name",
    "origin_text",
    "destination_text",
    "origin_load_date",
    "cargo_description",
    "weight_kg",
    "customer_price",
)

_MINIMUM_REQUIRED_FIELDS: tuple[str, ...] = (
    "customer_name",
    "origin_text",
    "destination_text",
    "origin_load_date",
    "cargo_description",
)

_FIELD_PREFIXES: tuple[tuple[str, str], ...] = (
    ("cliente", "customer_name"),
    ("customer", "customer_name"),
    ("origen", "origin_text"),
    ("origin", "origin_text"),
    ("pickup", "origin_text"),
    ("destino", "destination_text"),
    ("destination", "destination_text"),
    ("delivery", "destination_text"),
    ("fecha de carga", "origin_load_date"),
    ("fecha/hora de carga", "origin_load_date"),
    ("load date", "origin_load_date"),
    ("loading date", "origin_load_date"),
    ("pickup date", "origin_load_date"),
    ("fecha de descarga", "destination_unload_date"),
    ("fecha/hora de descarga", "destination_unload_date"),
    ("unload date", "destination_unload_date"),
    ("unloading date", "destination_unload_date"),
    ("delivery date", "destination_unload_date"),
    ("drop-off date", "destination_unload_date"),
    ("descripcion de la carga", "cargo_description"),
    ("descripción de la carga", "cargo_description"),
    ("mercancia", "cargo_description"),
    ("mercancía", "cargo_description"),
    ("cargo", "cargo_description"),
    ("commodity", "cargo_description"),
    ("presupuesto", "customer_price"),
    ("precio cliente", "customer_price"),
    ("precio", "customer_price"),
    ("price", "customer_price"),
    ("peso", "weight_kg"),
    ("weight", "weight_kg"),
    ("tipo de camion", "truck_type_id"),
    ("tipo de camión", "truck_type_id"),
    ("truck type", "truck_type_id"),
    ("currency", "currency"),
    ("adr", "adr_required"),
)

_TEXT_FIELDS: frozenset[str] = frozenset({
    "customer_name",
    "origin_text",
    "destination_text",
    "cargo_description",
})

_DECIMAL_FIELDS: frozenset[str] = frozenset({
    "distance_km",
    "weight_kg",
    "customer_price",
})

_DATETIME_FIELDS: frozenset[str] = frozenset({
    "origin_load_date",
    "destination_unload_date",
})

_INTEGER_FIELDS: frozenset[str] = frozenset({"truck_type_id"})

_RAW_TEXT_DATE_HINT_PATTERN = re.compile(
    r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b"
)

_COMPANY_SUFFIX_PATTERN = re.compile(
    r"\b(?:s\.?\s*l\.?|s\.?\s*a\.?|s\.?\s*r\.?\s*l\.?|gmbh|llc|ltd\.?|inc\.?|corp\.?|bv|b\.?\s*v\.?|nv|n\.?\s*v\.?|oy|ab|as|ag|sarl|sas|spa|s\.?\s*p\.?\s*a\.?)\b",
    re.IGNORECASE,
)

_COMPANY_KEYWORD_PATTERN = re.compile(
    r"\b(?:logistics|logistica|logística|transport|transporte|freight|cargo|shipping|global|industrial|quimica|química)\b",
    re.IGNORECASE,
)

_ROLE_OR_NOISE_PATTERN = re.compile(
    r"\b(?:manager|director|sales|export|import|operations|operaciones|comercial|coordinator|coordinador|department|team|equipo|saludos|regards|hello|hola)\b",
    re.IGNORECASE,
)

_EMAIL_OR_URL_PATTERN = re.compile(r"[@]|https?://|www\.", re.IGNORECASE)

_PERSON_NAME_PATTERN = re.compile(
    r"^[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ'’.-]+(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ'’.-]+){1,3}$"
)

_MODEL_FIELD_ALIASES: dict[str, str] = {
    "company_name": "customer_name",
    "customer": "customer_name",
    "truck_type": "truck_type_id",
}


def _normalize_lookup_text(raw_value: str) -> str:
    ascii_normalized = unicodedata.normalize("NFKD", raw_value)
    ascii_normalized = ascii_normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_normalized.strip().lower())

_TRUCK_TYPE_NAME_TO_ID = {
    _normalize_lookup_text(name): truck_type_id
    for truck_type_id, name in PROTOTYPE_TRUCK_TYPES
}

_TRUCK_TYPE_NAME_TO_ID.update(
    {
        "curtainsider": 1,
        "curtain sider": 1,
        "frigo": 2,
        "frigorifico": 2,
        "refrigerated": 2,
        "mega trailer": 3,
        "megatrailer": 3,
    }
)


class RawTextLoadOrderParserError(RuntimeError):
    """Raised when deterministic raw-text parsing cannot complete."""


class RawTextLoadOrderUserInputError(RawTextLoadOrderParserError):
    """Raised when raw text contains malformed user-provided values."""


class IngestionState(TypedDict):
    session: AsyncSession
    user_id: UUID
    raw_text: str
    ingestion_run: IngestionRun
    trace_steps: NotRequired[list[dict[str, object]]]
    extracted_payload: NotRequired[dict[str, Any]]
    missing_fields: NotRequired[dict[str, str]]
    load_order: NotRequired[LoadOrderResponse]


def _normalize_key(raw_key: str) -> str:
    return raw_key.strip().lower()


def _extract_value(raw_text: str, field_name: str) -> str | None:
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue

        raw_key, raw_value = line.split(":", 1)
        if _normalize_key(raw_key) == field_name:
            value = raw_value.strip()
            return value or None

    return None


def _split_company_candidate_fragments(raw_line: str) -> list[str]:
    return [
        fragment.strip(" ,;:-")
        for fragment in re.split(r"\s+\|\s+|\s+-\s+|\s+/\s+", raw_line)
        if fragment.strip(" ,;:-")
    ]


def _looks_like_company_name(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False

    return bool(
        _COMPANY_SUFFIX_PATTERN.search(normalized)
        or _COMPANY_KEYWORD_PATTERN.search(normalized)
    )


def _looks_like_person_name(value: str) -> bool:
    normalized = value.strip()
    if not normalized or _looks_like_company_name(normalized):
        return False

    return bool(_PERSON_NAME_PATTERN.fullmatch(normalized))


def _infer_customer_name_from_raw_text(raw_text: str) -> str | None:
    best_candidate: str | None = None
    best_score = 0
    best_index = -1

    for index, raw_line in enumerate(raw_text.splitlines()):
        line = raw_line.strip()
        if not line or ":" in line or _EMAIL_OR_URL_PATTERN.search(line):
            continue

        for fragment in _split_company_candidate_fragments(line):
            score = 0
            if _COMPANY_SUFFIX_PATTERN.search(fragment):
                score += 10
            if _COMPANY_KEYWORD_PATTERN.search(fragment):
                score += 3
            if _ROLE_OR_NOISE_PATTERN.search(fragment):
                score -= 6
            if _looks_like_person_name(fragment):
                score -= 6
            if any(ch.isdigit() for ch in fragment):
                score -= 2
            if len(fragment) < 4 or len(fragment) > 80:
                score -= 2

            if score > best_score or (score == best_score and score > 0 and index > best_index):
                best_candidate = fragment
                best_score = score
                best_index = index

    return best_candidate if best_score > 0 else None


def _parse_bool(raw_value: str) -> bool:
    normalized = raw_value.strip().lower()
    normalized_prefix = re.split(r"[,(]", normalized, maxsplit=1)[0].strip()
    normalized_prefix = re.sub(r"\s+", " ", normalized_prefix)
    if normalized_prefix in {"1", "true", "yes", "y", "si", "sí", "requerido", "requerida"}:
        return True

    if normalized_prefix in {
        "0",
        "false",
        "no",
        "n",
        "no requerido",
        "no requerida",
        "not required",
        "not needed",
    }:
        return False

    raise RawTextLoadOrderUserInputError("invalid adr value")


def _parse_datetime(raw_value: str) -> str:
    """Parse datetime from various formats and return ISO 8601 string."""
    cleaned = raw_value.strip()

    # Remove common Spanish time phrases and day names
    cleaned = re.sub(r'\s*a\s+las\s+', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*h\b', '', cleaned)
    cleaned = re.sub(r'\s*hours?\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b(?:próximo|proxima|next)\s+(?:lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b(?:lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\s+', '', cleaned, flags=re.IGNORECASE)

    # Try multiple date formats
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%d/%m %H:%M",
        "%d/%m",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            # If year is missing, use current year (2026)
            if parsed.year == 1900:
                parsed = parsed.replace(year=2026)
            return parsed.isoformat()
        except ValueError:
            continue

    # Try to extract date pattern from text like "15/06 08:30 (Muelle 4)"
    date_match = re.search(r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?(?:\s+\d{1,2}:\d{2})?)', cleaned)
    if date_match:
        date_str = date_match.group(1)
        for fmt in ["%d/%m/%Y %H:%M", "%d/%m/%Y", "%d/%m %H:%M", "%d/%m"]:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=2026)
                return parsed.isoformat()
            except ValueError:
                continue

    raise RawTextLoadOrderUserInputError("invalid load date format")


def _parse_decimal(raw_value: str) -> str:
    normalized = raw_value.strip().split()[0]
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif "," in normalized:
        normalized = normalized.replace(",", ".")
    elif normalized.count(".") > 1:
        normalized = normalized.replace(".", "")
    elif normalized.count(".") == 1:
        integer_part, fractional_part = normalized.split(".", 1)
        if fractional_part.isdigit() and len(fractional_part) == 3:
            normalized = f"{integer_part}{fractional_part}"
    try:
        return str(Decimal(normalized))
    except InvalidOperation as exc:
        raise RawTextLoadOrderUserInputError("invalid decimal value") from exc


def _parse_truck_type(raw_value: str) -> int:
    normalized = _normalize_lookup_text(raw_value)
    candidates = [normalized]
    candidates.extend(
        fragment
        for fragment in (
            _normalize_lookup_text(fragment)
            for fragment in re.split(r"[|/,;()]", raw_value)
        )
        if fragment
    )

    for candidate in candidates:
        truck_type_id = _TRUCK_TYPE_NAME_TO_ID.get(candidate)
        if truck_type_id is not None:
            return truck_type_id

    for candidate in candidates:
        for alias, truck_type_id in _TRUCK_TYPE_NAME_TO_ID.items():
            if re.search(rf"\b{re.escape(alias)}\b", candidate):
                return truck_type_id

    raise RawTextLoadOrderUserInputError("invalid truck type value")


def _parse_model_datetime(raw_value: Any) -> str:
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is not None:
            raw_value = raw_value.astimezone(timezone.utc).replace(tzinfo=None)
        return raw_value.isoformat()

    if not isinstance(raw_value, str):
        raise RawTextLoadOrderUserInputError("invalid load date format")

    stripped = raw_value.strip()
    if not stripped:
        raise RawTextLoadOrderUserInputError("invalid load date format")

    try:
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.isoformat()
    except ValueError:
        return _parse_datetime(stripped)


def _parse_model_decimal(raw_value: Any) -> str:
    if isinstance(raw_value, Decimal):
        return str(raw_value)

    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        return str(Decimal(str(raw_value)))

    if isinstance(raw_value, str):
        return _parse_decimal(raw_value)

    raise RawTextLoadOrderUserInputError("invalid decimal value")


def _parse_model_int(raw_value: Any) -> int:
    if isinstance(raw_value, bool):
        raise ValueError("invalid integer value")

    if isinstance(raw_value, int):
        return raw_value

    if isinstance(raw_value, str) and raw_value.strip():
        return int(raw_value.strip())

    raise ValueError("invalid integer value")


def _parse_model_truck_type(raw_value: Any) -> int:
    if isinstance(raw_value, bool):
        raise ValueError("invalid truck type value")

    if isinstance(raw_value, int):
        return raw_value

    if isinstance(raw_value, str) and raw_value.strip():
        stripped = raw_value.strip()
        if stripped.isdigit():
            return int(stripped)
        return _parse_truck_type(stripped)

    raise ValueError("invalid truck type value")


def _parse_model_currency(raw_value: Any) -> str:
    if not isinstance(raw_value, str):
        raise ValueError("invalid currency value")

    letters = "".join(ch for ch in raw_value.upper() if ch.isalpha())
    if len(letters) < 3:
        raise ValueError("invalid currency value")

    return letters[:3]


def parse_load_order_raw_text(raw_text: str) -> dict[str, Any]:
    """Extract a narrow deterministic payload from plain raw text."""

    extracted_payload: dict[str, Any] = {}

    for prefix, field_name in _FIELD_PREFIXES:
        raw_value = _extract_value(raw_text, prefix)
        if raw_value is None:
            continue

        if field_name == "origin_load_date":
            extracted_payload[field_name] = _parse_datetime(raw_value)
            continue

        if field_name == "destination_unload_date":
            extracted_payload[field_name] = _parse_datetime(raw_value)
            continue

        if field_name in {"customer_price", "weight_kg"}:
            extracted_payload[field_name] = _parse_decimal(raw_value)
            continue

        if field_name == "truck_type_id":
            extracted_payload[field_name] = _parse_truck_type(raw_value)
            continue

        if field_name == "adr_required":
            extracted_payload[field_name] = _parse_bool(raw_value)
            continue

        extracted_payload[field_name] = raw_value

    if "customer_name" not in extracted_payload:
        inferred_customer_name = _infer_customer_name_from_raw_text(raw_text)
        if inferred_customer_name:
            extracted_payload["customer_name"] = inferred_customer_name

    extracted_payload.setdefault("currency", "EUR")
    return extracted_payload


def _safe_parse_load_order_raw_text(raw_text: str) -> tuple[dict[str, Any], list[str]]:
    try:
        return parse_load_order_raw_text(raw_text), []
    except RawTextLoadOrderParserError as exc:
        return {}, [f"deterministic_fallback_failed:{exc}"]


def _raw_text_supports_datetime_extraction(raw_text: str) -> bool:
    normalized = raw_text.lower()
    if _RAW_TEXT_DATE_HINT_PATTERN.search(normalized):
        return True

    return any(
        marker in normalized
        for marker in (
            "load date",
            "loading date",
            "pickup date",
            "delivery date",
            "fecha de carga",
            "fecha de descarga",
        )
    )


def _normalize_model_extracted_payload(
    extracted_payload: dict[str, Any],
    raw_text: str,
) -> tuple[dict[str, Any], list[str]]:
    normalized_payload, warnings = _safe_parse_load_order_raw_text(raw_text)
    inferred_customer_name = _infer_customer_name_from_raw_text(raw_text)

    for raw_field_name, raw_value in extracted_payload.items():
        field_name = _MODEL_FIELD_ALIASES.get(raw_field_name, raw_field_name)
        if raw_value in (None, ""):
            continue

        try:
            if field_name == "customer_name":
                if normalized_payload.get("customer_name"):
                    continue
                value = str(raw_value).strip()
                if not value:
                    continue
                if inferred_customer_name and not _looks_like_company_name(value):
                    normalized_payload[field_name] = inferred_customer_name
                else:
                    normalized_payload[field_name] = value
                continue

            if field_name in _TEXT_FIELDS:
                value = str(raw_value).strip()
                if value:
                    normalized_payload[field_name] = value
                continue

            if field_name in _DATETIME_FIELDS:
                if field_name not in normalized_payload and not _raw_text_supports_datetime_extraction(raw_text):
                    warnings.append(f"discarded_ungrounded_model_field:{field_name}")
                    continue
                normalized_payload[field_name] = _parse_model_datetime(raw_value)
                continue

            if field_name in _DECIMAL_FIELDS:
                normalized_payload[field_name] = _parse_model_decimal(raw_value)
                continue

            if field_name == "adr_required":
                normalized_payload[field_name] = raw_value if isinstance(raw_value, bool) else _parse_bool(str(raw_value))
                continue

            if field_name == "truck_type_id":
                normalized_payload[field_name] = _parse_model_truck_type(raw_value)
                continue

            if field_name in _INTEGER_FIELDS:
                normalized_payload[field_name] = _parse_model_int(raw_value)
                continue

            if field_name == "currency":
                normalized_payload[field_name] = _parse_model_currency(raw_value)
                continue
        except (RawTextLoadOrderUserInputError, ValueError, TypeError):
            warnings.append(f"discarded_invalid_model_field:{field_name}")

    if "customer_name" not in normalized_payload and inferred_customer_name:
        normalized_payload["customer_name"] = inferred_customer_name

    normalized_payload.setdefault("currency", "EUR")
    return normalized_payload, warnings


def _build_missing_fields(extracted_payload: dict[str, Any]) -> dict[str, str]:
    return {
        field_name: "not_found"
        for field_name in _TRACKED_FIELDS
        if extracted_payload.get(field_name) in (None, "")
    }


def _resolve_load_order_status(missing_fields: dict[str, str]) -> LoadOrderStatus:
    minimum_missing_fields = {
        field_name: missing_fields[field_name]
        for field_name in _MINIMUM_REQUIRED_FIELDS
        if field_name in missing_fields
    }
    if minimum_missing_fields:
        return LoadOrderStatus.PENDING_INGESTION

    return LoadOrderStatus.VIABILITY_PENDING


async def _mark_ingestion_run_failed(
    session: AsyncSession,
    ingestion_run: IngestionRun,
    error_detail: str,
) -> None:
    ingestion_run.status = IngestionRunStatus.FAILED
    ingestion_run.error_detail = error_detail
    await session.flush()
    await session.commit()


def _build_load_order_payload(
    *,
    user_id: UUID,
    extracted_payload: dict[str, Any],
    missing_fields: dict[str, str],
) -> LoadOrderCreate:
    return LoadOrderCreate(
        user_id=user_id,
        customer_id=None,
        customer_name=extracted_payload.get("customer_name"),
        status=_resolve_load_order_status(missing_fields),
        origin_id=None,
        origin_text=extracted_payload.get("origin_text"),
        origin_load_date=(
            datetime.fromisoformat(extracted_payload["origin_load_date"])
            if "origin_load_date" in extracted_payload
            else None
        ),
        destination_id=None,
        destination_text=extracted_payload.get("destination_text"),
        cargo_description=extracted_payload.get("cargo_description"),
        weight_kg=(
            Decimal(extracted_payload["weight_kg"])
            if "weight_kg" in extracted_payload
            else None
        ),
        truck_type_id=extracted_payload.get("truck_type_id"),
        adr_required=bool(extracted_payload.get("adr_required", False)),
        missing_fields=missing_fields or None,
        customer_price=(
            Decimal(extracted_payload["customer_price"])
            if "customer_price" in extracted_payload
            else None
        ),
        currency=str(extracted_payload.get("currency", "EUR")),
    )


def _make_trace_step(node: str, outcome: str, **extra: object) -> dict[str, object]:
    step: dict[str, object] = {
        "node": node,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    step.update(extra)
    return step


async def _model_extract_node(state: IngestionState) -> IngestionState:
    settings = get_settings()
    trace_steps: list[dict[str, object]] = list(state.get("trace_steps", []))

    if not settings.ingestion_model_name:
        trace_steps.append(_make_trace_step("model_extract", "skipped", reason="no_model_configured"))
        trace_steps.append(_make_trace_step("fallback", "triggered"))
        state["extracted_payload"] = parse_load_order_raw_text(state["raw_text"])
        state["ingestion_run"].execution_path = "fallback"
        state["trace_steps"] = trace_steps
        return state

    try:
        result = await extract_load_order_with_model(state["raw_text"], settings)
        trace_steps.append(_make_trace_step("model_extract", "success"))
        extracted, normalization_warnings = _normalize_model_extracted_payload(
            dict(result.extracted_payload),
            state["raw_text"],
        )
        state["extracted_payload"] = extracted
        state["ingestion_run"].execution_path = "model"
        state["ingestion_run"].provider = result.provider
        state["ingestion_run"].model_name = result.model_name
        state["ingestion_run"].raw_model_response = result.raw_model_response
        state["ingestion_run"].confidence_summary = result.confidence_summary
        state["ingestion_run"].normalization_warnings = [
            *result.normalization_warnings,
            *normalization_warnings,
        ]
    except Exception:
        trace_steps.append(
            _make_trace_step("model_extract", "failure", reason="model_error")
        )
        trace_steps.append(_make_trace_step("fallback", "triggered"))
        state["extracted_payload"] = parse_load_order_raw_text(state["raw_text"])
        state["ingestion_run"].execution_path = "fallback"

    state["trace_steps"] = trace_steps
    return state


async def _ingestion_worker_node(state: IngestionState) -> IngestionState:
    extracted_payload = state["extracted_payload"]
    state["missing_fields"] = _build_missing_fields(extracted_payload)
    trace_steps: list[dict[str, object]] = list(state.get("trace_steps", []))
    trace_steps.append(_make_trace_step("normalize", "done"))
    state["trace_steps"] = trace_steps
    return state


async def _persist_load_order_node(state: IngestionState) -> IngestionState:
    payload = _build_load_order_payload(
        user_id=state["user_id"],
        extracted_payload=state["extracted_payload"],
        missing_fields=state["missing_fields"],
    )
    state["load_order"] = await create_load_order(state["session"], payload)
    trace_steps: list[dict[str, object]] = list(state.get("trace_steps", []))
    trace_steps.append(_make_trace_step("persist_load_order", "done"))
    state["trace_steps"] = trace_steps
    return state


def _build_ingestion_graph() -> Any:
    graph = StateGraph(IngestionState)
    graph.add_node("orchestrator", _model_extract_node)
    graph.add_node("ingestion_worker", _ingestion_worker_node)
    graph.add_node("persist_load_order", _persist_load_order_node)
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "ingestion_worker")
    graph.add_edge("ingestion_worker", "persist_load_order")
    graph.add_edge("persist_load_order", END)
    return graph.compile()


async def ingest_load_order_from_raw_text(
    session: AsyncSession,
    user_id: UUID,
    raw_text: str,
) -> LoadOrderIngestionResponse:
    """Persist an ingestion run and derived load order from raw text."""

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    ingestion_run = IngestionRun(
        user_id=user_id,
        route=LOAD_ORDER_INGESTION_ROUTE,
        raw_text=raw_text,
        status=IngestionRunStatus.PROCESSING,
    )
    session.add(ingestion_run)
    await session.flush()

    graph = _build_ingestion_graph()
    initial_state: IngestionState = {
        "session": session,
        "user_id": user_id,
        "raw_text": raw_text,
        "ingestion_run": ingestion_run,
        "trace_steps": [],
    }

    try:
        async with session.begin_nested():
            result = await graph.ainvoke(initial_state)
            extracted_payload = result["extracted_payload"]
            missing_fields = result["missing_fields"]
            load_order = result["load_order"]
            trace_steps = result["trace_steps"]

    except HTTPException as exc:
        await _mark_ingestion_run_failed(session, ingestion_run, str(exc.detail))
        raise

    except ValidationError as exc:
        await _mark_ingestion_run_failed(session, ingestion_run, str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except RawTextLoadOrderUserInputError as exc:
        await _mark_ingestion_run_failed(session, ingestion_run, str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:
        await _mark_ingestion_run_failed(session, ingestion_run, str(exc))
        raise HTTPException(
            status_code=500,
            detail="Load order ingestion failed",
        ) from exc

    ingestion_run.extracted_payload = extracted_payload
    ingestion_run.missing_fields = missing_fields
    ingestion_run.load_order_id = load_order.id
    ingestion_run.trace_steps = trace_steps
    ingestion_run.status = IngestionRunStatus.COMPLETED
    await session.flush()

    return LoadOrderIngestionResponse(
        ingestion_run_id=ingestion_run.id,
        route=LOAD_ORDER_INGESTION_ROUTE,
        run_status=ingestion_run.status,
        load_order=load_order,
        extracted_payload=extracted_payload,
        missing_fields=missing_fields,
        execution_path=ingestion_run.execution_path,
        provider=ingestion_run.provider,
        model_name=ingestion_run.model_name,
        trace_steps=trace_steps,
    )
