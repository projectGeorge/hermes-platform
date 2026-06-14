"""Shipment execution monitoring read/write services."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.backend.core.settings import get_settings
from app.backend.core.domain_enums import (
    ExecutionMonitoringStatus,
    LoadOrderStatus,
    MonitoringAlertStatus,
)
from app.backend.models.execution_monitoring_snapshot import ExecutionMonitoringSnapshot
from app.backend.models.load_order import LoadOrder
from app.backend.models.monitoring_alert import MonitoringAlert
from app.backend.models.trip import Trip
from app.backend.schemas.monitoring import ExecutionMonitoringReadModelResponse

_CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "madrid": (40.4168, -3.7038),
    "barcelona": (41.3874, 2.1686),
    "valencia": (39.4699, -0.3763),
    "zaragoza": (41.6488, -0.8891),
    "bilbao": (43.2630, -2.9350),
    "paris": (48.8566, 2.3522),
    "lyon": (45.7640, 4.8357),
    "marseille": (43.2965, 5.3698),
    "bordeaux": (44.8378, -0.5792),
    "toulouse": (43.6047, 1.4442),
    "berlin": (52.5200, 13.4050),
    "hamburg": (53.5511, 9.9937),
    "munich": (48.1351, 11.5820),
    "milan": (45.4642, 9.1900),
    "rome": (41.9028, 12.4964),
    "turin": (45.0703, 7.6869),
    "amsterdam": (52.3676, 4.9041),
    "brussels": (50.8503, 4.3517),
    "lisbon": (38.7223, -9.1393),
    "porto": (41.1579, -8.6291),
}

_CHECKPOINT_KINDS = ("origin", "linehaul", "border", "destination")
_ROUTE_GEOMETRY_VERSION = 2
_ROUTE_GEOMETRY_MAX_POINTS = 240
_MONITORING_PROVIDER_TIMEOUT_SECONDS = 15.0
_MAX_EXECUTION_INCIDENTS_PER_ORDER = 2
_AI_MONITORING_EVENT_TYPES = frozenset({
    "border_delay_detected",
    "unplanned_stop",
    "resumed_movement",
    "on_time_recovery",
})
_AI_MONITORING_SEVERITIES = frozenset({"info", "warning", "critical"})


class ModelMonitoringIncident(BaseModel):
    should_create: bool = False
    event_type: str = ""
    severity: str = "warning"
    title: str = ""
    detail: str = ""
    checkpoint_name: str | None = None
    operator_note: str | None = None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _normalize_place_label(text: str | None) -> str:
    if not text:
        return "Unknown"
    return text.strip()


def _city_key(text: str | None) -> str:
    label = _normalize_place_label(text)
    return label.split(",", 1)[0].strip().lower()


def _parse_country_code(text: str | None) -> str | None:
    if not text or "," not in text:
        return None
    country = text.rsplit(",", 1)[1].strip().upper()
    return country[:2] if country else None


def _maptiler_feature_country_code(feature: object) -> str | None:
    if not isinstance(feature, dict):
        return None

    properties = feature.get("properties")
    if isinstance(properties, dict):
        country_code = properties.get("country_code")
        if isinstance(country_code, str) and country_code.strip():
            return country_code.strip().upper()

    context = feature.get("context")
    if not isinstance(context, list):
        return None

    for entry in context:
        if not isinstance(entry, dict):
            continue
        country_code = entry.get("country_code")
        if isinstance(country_code, str) and country_code.strip():
            return country_code.strip().upper()

    return None


def _maptiler_coordinate_from_features(
    features: object,
    *,
    expected_country_code: str | None,
) -> dict[str, float]:
    if not isinstance(features, list):
        raise TypeError("MapTiler response features must be a list")

    for feature in features:
        if expected_country_code:
            feature_country_code = _maptiler_feature_country_code(feature)
            if feature_country_code != expected_country_code:
                continue

        if not isinstance(feature, dict):
            continue
        center = feature.get("center")
        if not isinstance(center, list) or len(center) < 2:
            continue
        return _route_coordinate(float(center[1]), float(center[0]))

    raise IndexError("No MapTiler feature matched the expected country")


def _coordinate_for_label(text: str | None, *, fallback_seed: int) -> tuple[float, float]:
    key = _city_key(text)
    if key in _CITY_COORDINATES:
        return _CITY_COORDINATES[key]

    normalized = _normalize_place_label(text)
    accumulator = sum((index + 1) * ord(character) for index, character in enumerate(normalized)) + fallback_seed
    lat = 36.0 + (accumulator % 1200) / 100.0
    lng = -9.5 + (accumulator % 2400) / 100.0
    return round(min(lat, 59.0), 4), round(min(lng, 24.0), 4)


def _interpolate(start: tuple[float, float], end: tuple[float, float], fraction: float) -> tuple[float, float]:
    lat = start[0] + (end[0] - start[0]) * fraction
    lng = start[1] + (end[1] - start[1]) * fraction
    return round(lat, 4), round(lng, 4)


def _route_coordinate(lat: float, lng: float) -> dict[str, float]:
    return {"lat": round(float(lat), 6), "lng": round(float(lng), 6)}


def _coordinate_dict_to_tuple(coordinate: dict[str, float]) -> tuple[float, float]:
    return float(coordinate["lat"]), float(coordinate["lng"])


def _coerce_coordinate(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    lat = value.get("lat")
    lng = value.get("lng")
    try:
        return _route_coordinate(float(lat), float(lng))
    except (TypeError, ValueError):
        return None


def _normalize_route_path(value: object) -> list[dict[str, float]]:
    if not isinstance(value, list):
        return []

    route_path: list[dict[str, float]] = []
    for point in value:
        coordinate = _coerce_coordinate(point)
        if coordinate is not None:
            route_path.append(coordinate)
    return route_path


def _distance_between_coordinates(start: tuple[float, float], end: tuple[float, float]) -> float:
    lat1 = math.radians(start[0])
    lat2 = math.radians(end[0])
    dlat = lat2 - lat1
    dlng = math.radians(end[1] - start[1])
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def _coordinate_at_fraction(route_path: list[dict[str, float]], fraction: float) -> tuple[float, float]:
    if not route_path:
        return 0.0, 0.0

    if len(route_path) == 1 or fraction <= 0:
        first = route_path[0]
        return float(first["lat"]), float(first["lng"])

    if fraction >= 1:
        last = route_path[-1]
        return float(last["lat"]), float(last["lng"])

    total_distance_km = 0.0
    segment_lengths: list[float] = []
    for index, point in enumerate(route_path[:-1]):
        start = _coordinate_dict_to_tuple(point)
        end = _coordinate_dict_to_tuple(route_path[index + 1])
        segment_distance = _distance_between_coordinates(start, end)
        segment_lengths.append(segment_distance)
        total_distance_km += segment_distance

    if total_distance_km <= 0:
        first = route_path[0]
        return float(first["lat"]), float(first["lng"])

    target_distance_km = total_distance_km * max(0.0, min(fraction, 1.0))
    traversed_km = 0.0
    for index, segment_distance in enumerate(segment_lengths):
        start = route_path[index]
        end = route_path[index + 1]
        if traversed_km + segment_distance >= target_distance_km:
            segment_fraction = 0.0 if segment_distance <= 0 else (target_distance_km - traversed_km) / segment_distance
            lat = float(start["lat"]) + (float(end["lat"]) - float(start["lat"])) * segment_fraction
            lng = float(start["lng"]) + (float(end["lng"]) - float(start["lng"])) * segment_fraction
            return round(lat, 6), round(lng, 6)
        traversed_km += segment_distance

    last = route_path[-1]
    return float(last["lat"]), float(last["lng"])


def _downsample_route_path(
    route_path: list[dict[str, float]],
    *,
    max_points: int = _ROUTE_GEOMETRY_MAX_POINTS,
) -> list[dict[str, float]]:
    if len(route_path) <= max_points:
        return route_path

    step = max(1, math.ceil((len(route_path) - 1) / (max_points - 1)))
    sampled = [route_path[index] for index in range(0, len(route_path) - 1, step)]
    sampled.append(route_path[-1])
    return sampled


def _route_geometry_signature(order: LoadOrder) -> dict[str, str]:
    settings = get_settings()
    requested_profile = settings.monitoring_route_profile.strip() or "driving-car"
    return {
        "origin_text": _normalize_place_label(order.origin_text),
        "destination_text": _normalize_place_label(order.destination_text),
        "geocoding_provider": settings.monitoring_geocoding_provider.strip().lower(),
        "routing_provider": settings.monitoring_routing_provider.strip().lower(),
        "route_profile": requested_profile,
    }


def _route_label(order: LoadOrder) -> str:
    return f"{_normalize_place_label(order.origin_text)} -> {_normalize_place_label(order.destination_text)}"


def _distance_km(order: LoadOrder) -> float:
    if order.distance_km is not None:
        return max(float(order.distance_km), 120.0)

    origin = _coordinate_for_label(order.origin_text, fallback_seed=11)
    destination = _coordinate_for_label(order.destination_text, fallback_seed=29)
    rough = ((origin[0] - destination[0]) ** 2 + (origin[1] - destination[1]) ** 2) ** 0.5 * 111
    return round(max(rough, 180.0), 1)


def _selected_carrier_name(order: LoadOrder) -> str | None:
    if order.selected_trip is not None and order.selected_trip.carrier is not None:
        return order.selected_trip.carrier.company_name
    return None


def _status_for_order(order: LoadOrder, *, progress_percent: int = 0) -> ExecutionMonitoringStatus:
    if order.status == LoadOrderStatus.CANCELLED:
        return ExecutionMonitoringStatus.DELAYED
    if progress_percent >= 100:
        return ExecutionMonitoringStatus.DELIVERED
    if progress_percent > 0:
        return ExecutionMonitoringStatus.IN_TRANSIT
    return ExecutionMonitoringStatus.PLANNED


def _ensure_monitoring_order_status(order: LoadOrder) -> None:
    if order.status != LoadOrderStatus.FORMALIZED:
        raise HTTPException(
            status_code=409,
            detail="Execution monitoring requires a formalized order",
        )


def _build_route_points(
    order: LoadOrder,
    *,
    origin_coord: tuple[float, float] | None = None,
    destination_coord: tuple[float, float] | None = None,
) -> list[dict[str, object]]:
    origin_label = _normalize_place_label(order.origin_text)
    destination_label = _normalize_place_label(order.destination_text)
    origin_coord = origin_coord or _coordinate_for_label(order.origin_text, fallback_seed=3)
    destination_coord = destination_coord or _coordinate_for_label(order.destination_text, fallback_seed=7)
    distance_km = _distance_km(order)

    country_transition = None
    origin_country = _parse_country_code(order.origin_text)
    destination_country = _parse_country_code(order.destination_text)
    if origin_country and destination_country and origin_country != destination_country:
        country_transition = f"{origin_country}/{destination_country} border"
    else:
        country_transition = "Regional transfer"

    linehaul_label = f"Linehaul corridor ({int(distance_km * 0.55)} km)"

    intermediates = [
        ("origin", origin_label, origin_coord, 0.0),
        ("linehaul", linehaul_label, _interpolate(origin_coord, destination_coord, 0.42), 42.0),
        ("border", country_transition, _interpolate(origin_coord, destination_coord, 0.68), 68.0),
        ("destination", destination_label, destination_coord, 100.0),
    ]

    points: list[dict[str, object]] = []
    for sequence, (kind, label, coord, progress_marker) in enumerate(intermediates):
        points.append(
            {
                "kind": kind,
                "label": label,
                "sequence": sequence,
                "lat": coord[0],
                "lng": coord[1],
                "progress_marker": progress_marker,
                "status": "pending",
            }
        )
    return points


def _build_route_path(route_points: list[dict[str, object]]) -> list[dict[str, float]]:
    path: list[dict[str, float]] = []
    for index, point in enumerate(route_points[:-1]):
        start = (float(point["lat"]), float(point["lng"]))
        end_point = route_points[index + 1]
        end = (float(end_point["lat"]), float(end_point["lng"]))
        steps = 4 if index == 0 else 3
        for step in range(steps):
            fraction = step / steps
            lat, lng = _interpolate(start, end, fraction)
            path.append({"lat": lat, "lng": lng})
    last = route_points[-1]
    path.append({"lat": float(last["lat"]), "lng": float(last["lng"])})
    return path


def _align_route_points_to_path(
    route_points: list[dict[str, object]],
    route_path: list[dict[str, float]],
) -> list[dict[str, object]]:
    if len(route_path) < 2:
        return route_points

    aligned_points: list[dict[str, object]] = []
    for point in route_points:
        lat, lng = _coordinate_at_fraction(route_path, float(point["progress_marker"]) / 100.0)
        aligned_points.append(
            {
                **point,
                "lat": lat,
                "lng": lng,
            }
        )

    aligned_points[0]["lat"] = float(route_path[0]["lat"])
    aligned_points[0]["lng"] = float(route_path[0]["lng"])
    aligned_points[-1]["lat"] = float(route_path[-1]["lat"])
    aligned_points[-1]["lng"] = float(route_path[-1]["lng"])
    return aligned_points


async def _resolve_coordinate_for_label(
    text: str | None,
    *,
    fallback_seed: int,
) -> tuple[dict[str, float], str]:
    fallback_coordinate = _route_coordinate(*_coordinate_for_label(text, fallback_seed=fallback_seed))
    settings = get_settings()
    provider = settings.monitoring_geocoding_provider.strip().lower()
    api_key = settings.monitoring_geocoding_api_key
    expected_country_code = _parse_country_code(text)
    if not api_key or _normalize_place_label(text) == "Unknown":
        return fallback_coordinate, "fallback_seed"

    try:
        async with httpx.AsyncClient(timeout=_MONITORING_PROVIDER_TIMEOUT_SECONDS) as client:
            if provider == "maptiler":
                response = await client.get(
                    f"https://api.maptiler.com/geocoding/{quote(_normalize_place_label(text))}.json",
                    params={
                        "key": api_key,
                        "limit": 5,
                        **({"country": expected_country_code.lower()} if expected_country_code else {}),
                    },
                )
                response.raise_for_status()
                payload = response.json()
                features = payload.get("features") or []
                return _maptiler_coordinate_from_features(
                    features,
                    expected_country_code=expected_country_code,
                ), provider

            response = await client.get(
                "https://api.opencagedata.com/geocode/v1/json",
                params={
                    "q": _normalize_place_label(text),
                    "key": api_key,
                    "limit": 1,
                    "no_annotations": 1,
                    "language": "en",
                },
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") or []
            geometry = results[0].get("geometry") or {}
            return _route_coordinate(float(geometry["lat"]), float(geometry["lng"])), provider
    except (IndexError, KeyError, TypeError, ValueError, httpx.RequestError, httpx.HTTPStatusError):
        return fallback_coordinate, "fallback_seed"


def _normalize_openrouteservice_coordinates(value: object) -> list[dict[str, float]]:
    if not isinstance(value, list):
        return []

    route_path: list[dict[str, float]] = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lng = float(point[0])
            lat = float(point[1])
        except (TypeError, ValueError):
            continue
        route_path.append(_route_coordinate(lat, lng))
    return route_path


async def _resolve_openrouteservice_route(
    origin_coordinate: dict[str, float],
    destination_coordinate: dict[str, float],
) -> tuple[list[dict[str, float]], str, str | None]:
    settings = get_settings()
    provider = settings.monitoring_routing_provider.strip().lower()
    api_key = settings.monitoring_routing_api_key
    if provider != "openrouteservice" or not api_key:
        return [], "fallback_interpolation", None

    requested_profile = settings.monitoring_route_profile.strip() or "driving-car"
    candidate_profiles = [requested_profile]
    if requested_profile != "driving-car":
        candidate_profiles.append("driving-car")

    for profile in candidate_profiles:
        try:
            async with httpx.AsyncClient(timeout=_MONITORING_PROVIDER_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{settings.monitoring_routing_base_url.rstrip('/')}/v2/directions/{profile}/geojson",
                    headers={"Authorization": api_key},
                    json={
                        "coordinates": [
                            [origin_coordinate["lng"], origin_coordinate["lat"]],
                            [destination_coordinate["lng"], destination_coordinate["lat"]],
                        ]
                    },
                )
                response.raise_for_status()
                payload = response.json()
                features = payload.get("features") or []
                geometry = features[0].get("geometry") or {}
                route_path = _normalize_openrouteservice_coordinates(geometry.get("coordinates"))
                if len(route_path) >= 2:
                    return _downsample_route_path(route_path), "openrouteservice", profile
        except (IndexError, KeyError, TypeError, ValueError, httpx.RequestError, httpx.HTTPStatusError):
            continue

    return [], "fallback_interpolation", None


def _build_fallback_route_path(
    order: LoadOrder,
    origin_coordinate: dict[str, float],
    destination_coordinate: dict[str, float],
) -> list[dict[str, float]]:
    route_points = _build_route_points(
        order,
        origin_coord=_coordinate_dict_to_tuple(origin_coordinate),
        destination_coord=_coordinate_dict_to_tuple(destination_coordinate),
    )
    return _build_route_path(route_points)


async def _resolve_route_geometry(
    order: LoadOrder,
    metadata: dict[str, object] | None,
    *,
    force_refresh: bool = False,
) -> dict[str, object]:
    route_signature = _route_geometry_signature(order)
    stored_metadata = metadata or {}
    stored_route_path = _normalize_route_path(stored_metadata.get("route_path"))
    if (
        not force_refresh
        and str(stored_metadata.get("route_geometry_source")) != "fallback_interpolation"
        and
        stored_metadata.get("route_geometry_version") == _ROUTE_GEOMETRY_VERSION
        and stored_metadata.get("route_signature") == route_signature
        and len(stored_route_path) >= 2
    ):
        origin_coordinate = _coerce_coordinate(stored_metadata.get("origin_coordinate")) or stored_route_path[0]
        destination_coordinate = _coerce_coordinate(stored_metadata.get("destination_coordinate")) or stored_route_path[-1]
        return {
            "route_path": stored_route_path,
            "route_geometry_version": _ROUTE_GEOMETRY_VERSION,
            "route_signature": route_signature,
            "route_geometry_source": str(stored_metadata.get("route_geometry_source") or "persisted"),
            "origin_coordinate": origin_coordinate,
            "destination_coordinate": destination_coordinate,
            "origin_coordinate_source": str(stored_metadata.get("origin_coordinate_source") or "persisted"),
            "destination_coordinate_source": str(stored_metadata.get("destination_coordinate_source") or "persisted"),
            "route_profile": str(stored_metadata.get("route_profile") or get_settings().monitoring_route_profile.strip() or "driving-car"),
        }

    origin_coordinate, origin_source = await _resolve_coordinate_for_label(order.origin_text, fallback_seed=3)
    destination_coordinate, destination_source = await _resolve_coordinate_for_label(order.destination_text, fallback_seed=7)
    route_path, route_source, route_profile = await _resolve_openrouteservice_route(origin_coordinate, destination_coordinate)
    if len(route_path) < 2:
        if len(stored_route_path) >= 2:
            route_path = stored_route_path
            route_source = "persisted"
        else:
            route_path = _build_fallback_route_path(order, origin_coordinate, destination_coordinate)
            route_source = "fallback_interpolation"

    route_path = _downsample_route_path(route_path)
    if len(route_path) < 2:
        route_path = [origin_coordinate, destination_coordinate]

    return {
        "route_path": route_path,
        "route_geometry_version": _ROUTE_GEOMETRY_VERSION,
        "route_signature": route_signature,
        "route_geometry_source": route_source,
        "origin_coordinate": route_path[0],
        "destination_coordinate": route_path[-1],
        "origin_coordinate_source": origin_source,
        "destination_coordinate_source": destination_source,
        "route_profile": route_profile or (get_settings().monitoring_route_profile.strip() or "driving-car"),
    }


def _event_time(anchor: datetime, hours_offset: float) -> datetime:
    return anchor + timedelta(hours=hours_offset)


def _build_monitoring_initialized_event(order: LoadOrder, anchor: datetime) -> dict[str, object]:
    return {
        "event_type": "monitoring_initialized",
        "title": "Monitoring session initialized",
        "detail": f"Hermes prepared route supervision for {_route_label(order)}.",
        "checkpoint_name": _normalize_place_label(order.origin_text),
        "occurred_at": anchor.isoformat(),
        "severity": "info",
    }


def _serialize_alert(alert: MonitoringAlert) -> dict[str, object]:
    return {
        "id": str(alert.id),
        "load_order_id": str(alert.load_order_id) if alert.load_order_id is not None else None,
        "alert_type": alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type),
        "title": alert.title,
        "detail": alert.detail,
        "severity": alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
        "status": alert.status.value if hasattr(alert.status, "value") else str(alert.status),
        "dedupe_key": alert.dedupe_key,
        "metadata": alert.extra_metadata,
        "created_at": alert.created_at,
        "resolved_at": alert.resolved_at,
    }


def _deterministic_progress_increment(order: LoadOrder, refresh_count: int) -> int:
    route_signal = sum(ord(char) for char in _route_label(order))
    distance_bucket = int(_distance_km(order) // 150)
    return 14 + ((route_signal + refresh_count + distance_bucket) % 16)


def _current_position_for_progress(
    route_points: list[dict[str, object]],
    progress_percent: int,
) -> dict[str, object]:
    progress = max(0, min(progress_percent, 100))
    if progress <= 0:
        first = route_points[0]
        return {
            "label": str(first["label"]),
            "lat": float(first["lat"]),
            "lng": float(first["lng"]),
            "progress_percent": progress,
        }

    for index, point in enumerate(route_points[1:], start=1):
        marker = float(point["progress_marker"])
        previous = route_points[index - 1]
        previous_marker = float(previous["progress_marker"])
        if progress <= marker:
            segment_fraction = 1.0 if marker == previous_marker else (progress - previous_marker) / (marker - previous_marker)
            lat, lng = _interpolate(
                (float(previous["lat"]), float(previous["lng"])),
                (float(point["lat"]), float(point["lng"])),
                segment_fraction,
            )
            label = str(point["label"]) if progress >= marker else f"Approaching {point['label']}"
            return {
                "label": label,
                "lat": lat,
                "lng": lng,
                "progress_percent": progress,
            }

    last = route_points[-1]
    return {
        "label": str(last["label"]),
        "lat": float(last["lat"]),
        "lng": float(last["lng"]),
        "progress_percent": progress,
    }


def _status_for_checkpoint(point: dict[str, object], progress_percent: int) -> str:
    marker = float(point["progress_marker"])
    if progress_percent >= marker:
        return "completed"
    if progress_percent >= max(marker - 18, 0):
        return "active"
    return "pending"


def _event_exists(events: list[dict[str, object]], event_type: str) -> bool:
    return any(str(event.get("event_type")) == event_type for event in events)


def _append_event_if_missing(events: list[dict[str, object]], event: dict[str, object]) -> None:
    if not _event_exists(events, str(event["event_type"])):
        events.append(event)


def _execution_incident_count(alerts: list[dict[str, object]]) -> int:
    return sum(1 for alert in alerts if str(alert.get("alert_type")) == "execution_incident")


def _can_open_incident_slot(
    events: list[dict[str, object]],
    alerts: list[dict[str, object]],
    progress_percent: int,
) -> bool:
    if progress_percent < 35 or progress_percent >= 100:
        return False
    if _execution_incident_count(alerts) >= _MAX_EXECUTION_INCIDENTS_PER_ORDER:
        return False
    return True


def _validate_ai_incident(raw: dict[str, object]) -> ModelMonitoringIncident | None:
    try:
        incident = ModelMonitoringIncident(**raw)
    except Exception:
        return None

    if not incident.should_create:
        return incident
    if incident.event_type not in _AI_MONITORING_EVENT_TYPES:
        return None
    if incident.severity not in _AI_MONITORING_SEVERITIES:
        return None
    if not incident.title.strip() or not incident.detail.strip():
        return None
    return incident


def _build_incident_payload(
    *,
    order: LoadOrder,
    refresh_count: int,
    anchor: datetime,
    incident: ModelMonitoringIncident,
) -> tuple[dict[str, object], dict[str, object]]:
    checkpoint_name = incident.checkpoint_name or (
        "FR/ES border" if _parse_country_code(order.origin_text) != _parse_country_code(order.destination_text) else "linehaul corridor"
    )
    occurred_at = _event_time(anchor, 1.8).isoformat()
    event = {
        "event_type": incident.event_type,
        "title": incident.title.strip(),
        "detail": incident.detail.strip(),
        "checkpoint_name": checkpoint_name,
        "occurred_at": occurred_at,
        "severity": incident.severity,
    }
    alert = {
        "id": f"execution-{refresh_count}-{incident.event_type}",
        "load_order_id": str(order.id),
        "alert_type": "execution_incident",
        "title": incident.title.strip(),
        "detail": incident.detail.strip(),
        "severity": incident.severity,
        "status": "open",
        "dedupe_key": f"execution_incident:{order.id}:{incident.event_type}",
        "metadata": {
            "source": "ai_monitoring_incident",
            "refresh_count": refresh_count,
            "operator_note": incident.operator_note.strip() if incident.operator_note else None,
        },
        "created_at": occurred_at,
        "resolved_at": None,
    }
    return event, alert


async def _generate_bounded_ai_incident(
    *,
    order: LoadOrder,
    snapshot: ExecutionMonitoringSnapshot,
    refresh_count: int,
    checkpoint_name: str,
    anchor: datetime,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    settings = get_settings()
    if not settings.reasoning_model_name:
        return None, None

    from app.backend.services.model_runtime_gateway import structured_completion

    prompt = "\n".join([
        f"Route: {_route_label(order)}",
        f"Progress percent: {snapshot.progress_percent}",
        f"Current checkpoint: {snapshot.current_checkpoint or checkpoint_name}",
        f"Refresh count: {refresh_count}",
        f"Existing execution incidents: {_execution_incident_count(snapshot.alerts)}",
        "Allowed event_type values: border_delay_detected, unplanned_stop, resumed_movement, on_time_recovery.",
        "Allowed severity values: info, warning, critical.",
        "Return should_create=false if no bounded incident should be added.",
    ])

    try:
        result = await structured_completion(
            settings=settings,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Hermes' monitoring incident generator. Return valid JSON with keys: "
                        "should_create (boolean), event_type (string), severity (string), title (string), detail (string), checkpoint_name (string or null), operator_note (string or null). "
                        "Stay within the allowed values and do not invent route changes, progress changes, checkpoint changes, or delivery state changes. "
                        "If the provided state does not justify a bounded incident, return should_create=false."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            profile="reasoning",
        )
    except Exception:
        return None, None

    content = result.content if isinstance(result.content, dict) else None
    if content is None:
        return None, None

    incident = _validate_ai_incident(content)
    if incident is None or not incident.should_create:
        return None, None

    return _build_incident_payload(
        order=order,
        refresh_count=refresh_count,
        anchor=anchor,
        incident=incident,
    )


def _maybe_build_incident(order: LoadOrder, progress_percent: int, refresh_count: int, anchor: datetime) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    signal = (sum(ord(char) for char in _route_label(order)) + refresh_count) % 5
    if progress_percent < 35 or progress_percent >= 100 or signal not in {1, 3}:
        return None, None

    checkpoint_name = "FR/ES border" if _parse_country_code(order.origin_text) != _parse_country_code(order.destination_text) else "linehaul corridor"
    event = {
        "event_type": "border_delay_detected" if signal == 1 else "unplanned_stop",
        "title": "Border delay detected" if signal == 1 else "Unplanned stop detected",
        "detail": "Traffic controls extended checkpoint handling by 45 minutes." if signal == 1 else "Vehicle stopped longer than expected for route pacing review.",
        "checkpoint_name": checkpoint_name,
        "occurred_at": _event_time(anchor, 1.8).isoformat(),
        "severity": "warning",
    }
    alert = {
        "id": f"execution-{refresh_count}-{event['event_type']}",
        "load_order_id": str(order.id),
        "alert_type": "execution_incident",
        "title": event["title"],
        "detail": event["detail"],
        "severity": "warning",
        "status": "open",
        "dedupe_key": f"execution_incident:{order.id}:{event['event_type']}",
        "metadata": {"source": "simulation", "refresh_count": refresh_count},
        "created_at": _event_time(anchor, 1.8).isoformat(),
        "resolved_at": None,
    }
    return event, alert


async def _select_incident_for_refresh(
    *,
    order: LoadOrder,
    snapshot: ExecutionMonitoringSnapshot,
    events: list[dict[str, object]],
    alerts: list[dict[str, object]],
    progress_percent: int,
    refresh_count: int,
    anchor: datetime,
    allow_cloud_reasoning: bool,
    checkpoint_name: str,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if not _can_open_incident_slot(events, alerts, progress_percent):
        return None, None

    if allow_cloud_reasoning:
        ai_event, ai_alert = await _generate_bounded_ai_incident(
            order=order,
            snapshot=snapshot,
            refresh_count=refresh_count,
            checkpoint_name=checkpoint_name,
            anchor=anchor,
        )
        if ai_event is not None and ai_alert is not None:
            if _event_exists(events, str(ai_event["event_type"])):
                return None, None
            if any(str(alert.get("dedupe_key")) == str(ai_alert["dedupe_key"]) for alert in alerts):
                return None, None
            last_incident_event_type = next(
                (
                    str(event.get("event_type"))
                    for event in reversed(events)
                    if str(event.get("event_type")) in _AI_MONITORING_EVENT_TYPES
                ),
                None,
            )
            if last_incident_event_type == str(ai_event["event_type"]):
                return None, None
            return ai_event, ai_alert

    return _maybe_build_incident(order, progress_percent, refresh_count, anchor)


async def _generate_cloud_agent_update(order: LoadOrder, snapshot: ExecutionMonitoringSnapshot) -> dict[str, object] | None:
    from app.backend.core.settings import get_settings
    from app.backend.services.model_runtime_gateway import structured_completion

    settings = get_settings()
    if not settings.reasoning_model_name:
        return None

    summary_parts = [
        f"Route: {_route_label(order)}",
        f"Status: {snapshot.status.value}",
        f"Progress: {snapshot.progress_percent}%",
        f"Current checkpoint: {snapshot.current_checkpoint or 'unknown'}",
    ]
    if order.cargo_description:
        summary_parts.append(f"Cargo: {order.cargo_description}")
    if snapshot.alerts:
        summary_parts.append(f"Active incidents: {len(snapshot.alerts)}")

    try:
        result = await structured_completion(
            settings=settings,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Hermes' shipment monitoring agent. Given the persisted shipment state, return valid JSON with keys: "
                        "summary (string), incident_summary (string or null), operator_note (string or null). "
                        "Be concise, operational, and avoid inventing new facts beyond the provided state. "
                        "If incidents are absent, say so plainly instead of implying one."
                    ),
                },
                {"role": "user", "content": "\n".join(summary_parts)},
            ],
            profile="reasoning",
        )
    except Exception:
        return None

    content = result.content
    if not isinstance(content, dict):
        return None

    summary = content.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None

    incident_summary = content.get("incident_summary")
    operator_note = content.get("operator_note")
    generated_at = _now()
    return {
        "source": "cloud",
        "summary": summary.strip(),
        "incident_summary": incident_summary.strip() if isinstance(incident_summary, str) and incident_summary.strip() else None,
        "operator_note": operator_note.strip() if isinstance(operator_note, str) and operator_note.strip() else None,
        "generated_at": generated_at.isoformat(),
        "provider": settings.reasoning_model_provider,
        "model_name": settings.reasoning_model_name,
    }


def _build_deterministic_agent_update(snapshot: ExecutionMonitoringSnapshot) -> dict[str, object]:
    current_position = (snapshot.extra_metadata or {}).get("current_position", {})
    current_label = current_position.get("label", snapshot.current_checkpoint or "route start")
    if snapshot.status == ExecutionMonitoringStatus.DELIVERED:
        summary = f"Shipment reached {current_label}. Hermes marked the route as completed."
        operator_note = "Arrival confirmed. Keep monitoring page as final execution record."
    elif snapshot.status == ExecutionMonitoringStatus.DELAYED:
        summary = f"Shipment supervision shows a delay signal near {current_label}."
        operator_note = "Review incidents and coordinate with carrier if delay persists."
    elif snapshot.status == ExecutionMonitoringStatus.IN_TRANSIT:
        summary = f"Shipment is in transit and currently tracking near {current_label}."
        operator_note = "Refresh on operator request to persist the next route update."
    else:
        summary = "Shipment is planned and waiting for execution movement to begin."
        operator_note = "Use refresh when the route should begin progressing."

    incident_summary = None
    if snapshot.alerts:
        latest_alert = snapshot.alerts[-1]
        incident_summary = str(latest_alert.get("title"))

    return {
        "source": "deterministic",
        "summary": summary,
        "incident_summary": incident_summary,
        "operator_note": operator_note,
        "generated_at": _now().isoformat(),
    }


async def _load_monitoring_snapshot(session: AsyncSession, order_id: UUID) -> ExecutionMonitoringSnapshot | None:
    stmt = select(ExecutionMonitoringSnapshot).where(ExecutionMonitoringSnapshot.load_order_id == order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _load_order_for_monitoring(session: AsyncSession, order_id: UUID) -> LoadOrder | None:
    stmt = (
        select(LoadOrder)
        .options(
            selectinload(LoadOrder.selected_trip).selectinload(Trip.carrier),
            selectinload(LoadOrder.trips).selectinload(Trip.carrier),
        )
        .where(LoadOrder.id == order_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _load_open_monitoring_alerts(session: AsyncSession, order_id: UUID) -> list[MonitoringAlert]:
    stmt = (
        select(MonitoringAlert)
        .where(
            MonitoringAlert.load_order_id == order_id,
            MonitoringAlert.status == MonitoringAlertStatus.OPEN,
        )
        .order_by(MonitoringAlert.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _current_position_for_progress_along_path(
    route_points: list[dict[str, object]],
    route_path: list[dict[str, float]],
    progress_percent: int,
) -> dict[str, object]:
    progress = max(0, min(progress_percent, 100))
    if not route_points:
        return {
            "label": "Unknown",
            "lat": 0.0,
            "lng": 0.0,
            "progress_percent": progress,
        }

    if len(route_path) < 2:
        return _current_position_for_progress(route_points, progress)

    lat, lng = _coordinate_at_fraction(route_path, progress / 100.0)
    first = route_points[0]
    if progress <= 0:
        return {
            "label": str(first["label"]),
            "lat": lat,
            "lng": lng,
            "progress_percent": progress,
        }

    for point in route_points[1:]:
        marker = float(point["progress_marker"])
        if progress <= marker:
            label = str(point["label"]) if progress >= marker else f"Approaching {point['label']}"
            return {
                "label": label,
                "lat": lat,
                "lng": lng,
                "progress_percent": progress,
            }

    last = route_points[-1]
    return {
        "label": str(last["label"]),
        "lat": lat,
        "lng": lng,
        "progress_percent": progress,
    }


async def _build_route_state(
    order: LoadOrder,
    metadata: dict[str, object] | None,
    *,
    force_route_refresh: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    route_geometry = await _resolve_route_geometry(order, metadata, force_refresh=force_route_refresh)
    origin_coordinate = _coordinate_dict_to_tuple(route_geometry["origin_coordinate"])
    destination_coordinate = _coordinate_dict_to_tuple(route_geometry["destination_coordinate"])
    route_points = _align_route_points_to_path(
        _build_route_points(order, origin_coord=origin_coordinate, destination_coord=destination_coordinate),
        route_geometry["route_path"],
    )
    return route_points, route_geometry


def _merge_route_metadata(
    metadata: dict[str, object],
    route_geometry: dict[str, object],
    *,
    current_position: dict[str, object],
) -> dict[str, object]:
    return {
        **metadata,
        "route_path": route_geometry["route_path"],
        "route_geometry_version": route_geometry["route_geometry_version"],
        "route_signature": route_geometry["route_signature"],
        "route_geometry_source": route_geometry["route_geometry_source"],
        "route_profile": route_geometry["route_profile"],
        "origin_coordinate": route_geometry["origin_coordinate"],
        "destination_coordinate": route_geometry["destination_coordinate"],
        "origin_coordinate_source": route_geometry["origin_coordinate_source"],
        "destination_coordinate_source": route_geometry["destination_coordinate_source"],
        "current_position": current_position,
    }


def _base_snapshot_metadata(
    order: LoadOrder,
    route_geometry: dict[str, object],
    route_points: list[dict[str, object]],
    *,
    source: str,
) -> dict[str, object]:
    route_path = list(route_geometry["route_path"])
    current_position = _current_position_for_progress_along_path(route_points, route_path, 0)
    return {
        "initialization_source": source,
        "load_order_status": order.status.value,
        "refresh_count": 0,
        "last_refresh_source": source,
        "route_label": _route_label(order),
        "agent_update": {
            "source": "deterministic",
            "summary": "Monitoring initialized. Hermes is ready to supervise route execution.",
            "incident_summary": None,
            "operator_note": "Use refresh to persist the next execution update.",
            "generated_at": _now().isoformat(),
        },
        "route_path": route_path,
        "route_geometry_version": route_geometry["route_geometry_version"],
        "route_signature": route_geometry["route_signature"],
        "route_geometry_source": route_geometry["route_geometry_source"],
        "route_profile": route_geometry["route_profile"],
        "origin_coordinate": route_geometry["origin_coordinate"],
        "destination_coordinate": route_geometry["destination_coordinate"],
        "origin_coordinate_source": route_geometry["origin_coordinate_source"],
        "destination_coordinate_source": route_geometry["destination_coordinate_source"],
        "current_position": current_position,
    }


async def ensure_execution_monitoring_snapshot(
    session: AsyncSession,
    order: LoadOrder,
    *,
    source: str,
) -> ExecutionMonitoringSnapshot:
    _ensure_monitoring_order_status(order)
    existing = await _load_monitoring_snapshot(session, order.id)
    existing_metadata = dict(existing.extra_metadata or {}) if existing is not None and existing.extra_metadata is not None else None
    progress_percent = int(existing.progress_percent or 0) if existing is not None else 0
    route_points, route_geometry = await _build_route_state(order, existing_metadata)
    current_position = _current_position_for_progress_along_path(route_points, route_geometry["route_path"], progress_percent)

    if existing is not None:
        for point in route_points:
            point["status"] = _status_for_checkpoint(point, progress_percent)
        metadata = _merge_route_metadata(
            {
            **(existing.extra_metadata or {}),
            "load_order_status": order.status.value,
            "last_sync_source": source,
            "route_label": _route_label(order),
            },
            route_geometry,
            current_position=current_position,
        )
        if "agent_update" not in metadata:
            metadata["agent_update"] = {
                "source": "deterministic",
                "summary": "Monitoring snapshot synchronized with latest order data.",
                "incident_summary": None,
                "operator_note": "Refresh when you want a new persisted execution update.",
                "generated_at": _now().isoformat(),
            }
        existing.status = _status_for_order(order, progress_percent=progress_percent)
        existing.current_checkpoint = next((str(point["label"]) for point in route_points if point["status"] == "active"), existing.current_checkpoint)
        existing.route_points = route_points
        existing.extra_metadata = metadata
        existing.last_refreshed_at = _now()
        await session.flush()
        return existing

    for point in route_points:
        point["status"] = _status_for_checkpoint(point, 0)
    created_at = _now()
    snapshot = ExecutionMonitoringSnapshot(
        load_order_id=order.id,
        status=_status_for_order(order),
        progress_percent=0,
        current_checkpoint=_normalize_place_label(order.origin_text),
        route_points=route_points,
        events=[_build_monitoring_initialized_event(order, created_at)],
        alerts=[],
        extra_metadata=_base_snapshot_metadata(order, route_geometry, route_points, source=source),
        last_refreshed_at=created_at,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def refresh_execution_monitoring_snapshot(
    session: AsyncSession,
    order: LoadOrder,
    *,
    source: str,
    allow_cloud_reasoning: bool = False,
) -> ExecutionMonitoringSnapshot:
    snapshot = await ensure_execution_monitoring_snapshot(session, order, source=source)
    metadata = dict(snapshot.extra_metadata or {})
    refresh_count = int(metadata.get("refresh_count", 0)) + 1
    previous_progress = int(snapshot.progress_percent or 0)
    progress_increment = _deterministic_progress_increment(order, refresh_count)
    progress_percent = min(100, previous_progress + progress_increment)

    route_points, route_geometry = await _build_route_state(order, metadata, force_route_refresh=True)
    route_path = list(route_geometry["route_path"])
    for point in route_points:
        point["status"] = _status_for_checkpoint(point, progress_percent)

    events = [dict(event) for event in (snapshot.events or [])]
    refresh_anchor = (snapshot.last_refreshed_at or _now()) + timedelta(hours=max(progress_increment / 8, 1))
    if progress_percent > 0:
        _append_event_if_missing(
            events,
            {
                "event_type": "pickup_completed",
                "title": "Pickup completed",
                "detail": "Shipment was released from origin handling and assigned to the route.",
                "checkpoint_name": _normalize_place_label(order.origin_text),
                "occurred_at": _event_time(refresh_anchor, 0.2).isoformat(),
                "severity": "info",
            },
        )
        _append_event_if_missing(
            events,
            {
                "event_type": "departed_origin",
                "title": "Departed origin",
                "detail": f"Vehicle left {_normalize_place_label(order.origin_text)} and entered the monitored corridor.",
                "checkpoint_name": _normalize_place_label(order.origin_text),
                "occurred_at": _event_time(refresh_anchor, 0.6).isoformat(),
                "severity": "info",
            },
        )
    if progress_percent >= 45:
        _append_event_if_missing(
            events,
            {
                "event_type": "linehaul_checkpoint_reached",
                "title": "Linehaul checkpoint reached",
                "detail": "Shipment crossed the mid-route corridor checkpoint within expected pacing.",
                "checkpoint_name": str(route_points[1]["label"]),
                "occurred_at": _event_time(refresh_anchor, 1.2).isoformat(),
                "severity": "info",
            },
        )
    if progress_percent >= 72:
        _append_event_if_missing(
            events,
            {
                "event_type": "resumed_movement",
                "title": "Resumed movement",
                "detail": "Shipment cleared the monitored bottleneck and returned to scheduled pace.",
                "checkpoint_name": str(route_points[2]["label"]),
                "occurred_at": _event_time(refresh_anchor, 1.6).isoformat(),
                "severity": "info",
            },
        )
    if progress_percent >= 100:
        _append_event_if_missing(
            events,
            {
                "event_type": "delivered",
                "title": "Delivered",
                "detail": f"Shipment arrived at {_normalize_place_label(order.destination_text)}.",
                "checkpoint_name": _normalize_place_label(order.destination_text),
                "occurred_at": _event_time(refresh_anchor, 2.0).isoformat(),
                "severity": "info",
            },
        )

    simulated_alerts = [dict(alert) for alert in (snapshot.alerts or []) if str(alert.get("status")) == "open"]
    incident_checkpoint_name = str(route_points[2]["label"]) if len(route_points) > 2 else snapshot.current_checkpoint or "linehaul corridor"
    incident_event, incident_alert = await _select_incident_for_refresh(
        order=order,
        snapshot=snapshot,
        events=events,
        alerts=simulated_alerts,
        progress_percent=progress_percent,
        refresh_count=refresh_count,
        anchor=refresh_anchor,
        allow_cloud_reasoning=allow_cloud_reasoning,
        checkpoint_name=incident_checkpoint_name,
    )
    if incident_event is not None and not _event_exists(events, str(incident_event["event_type"])):
        events.append(incident_event)
    if incident_alert is not None and not any(str(alert.get("dedupe_key")) == str(incident_alert["dedupe_key"]) for alert in simulated_alerts):
        simulated_alerts.append(incident_alert)

    current_position = _current_position_for_progress_along_path(route_points, route_path, progress_percent)
    status = _status_for_order(order, progress_percent=progress_percent)
    if incident_alert is not None and progress_percent < 100:
        status = ExecutionMonitoringStatus.DELAYED
    if progress_percent >= 100:
        simulated_alerts = []

    snapshot.progress_percent = progress_percent
    snapshot.status = status
    active_checkpoint = next((point for point in route_points if point["status"] == "active"), route_points[-1])
    snapshot.current_checkpoint = str(active_checkpoint["label"])
    snapshot.route_points = route_points
    snapshot.events = sorted(events, key=lambda event: str(event.get("occurred_at")))
    snapshot.alerts = simulated_alerts
    metadata = _merge_route_metadata(
        {
            **metadata,
            "load_order_status": order.status.value,
            "refresh_count": refresh_count,
            "last_refresh_source": source,
            "route_label": _route_label(order),
        },
        route_geometry,
        current_position=current_position,
    )
    snapshot.last_refreshed_at = _now()
    snapshot.extra_metadata = metadata

    agent_update = _build_deterministic_agent_update(snapshot)
    if allow_cloud_reasoning:
        cloud_agent_update = await _generate_cloud_agent_update(order, snapshot)
        if cloud_agent_update is not None:
            agent_update = cloud_agent_update
    metadata["agent_update"] = agent_update
    snapshot.extra_metadata = metadata
    await session.flush()
    return snapshot


def _build_shipment_summary(order: LoadOrder, snapshot: ExecutionMonitoringSnapshot) -> dict[str, object]:
    metadata = snapshot.extra_metadata or {}
    current_status_label = snapshot.status.value.replace("_", " ").title()
    return {
        "route_label": _route_label(order),
        "customer_name": order.customer_name,
        "cargo_description": order.cargo_description,
        "carrier_name": _selected_carrier_name(order),
        "distance_km": round(_distance_km(order), 1),
        "current_status_label": current_status_label,
        "last_update_source": str(metadata.get("last_refresh_source") or metadata.get("initialization_source") or "unknown"),
    }


async def get_execution_monitoring_read_model(
    session: AsyncSession,
    order_id: UUID,
) -> ExecutionMonitoringReadModelResponse:
    order = await _load_order_for_monitoring(session, order_id)
    if order is None:
        snapshot = await _load_monitoring_snapshot(session, order_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Execution monitoring snapshot not initialized")
        raise HTTPException(status_code=404, detail="Load order not found")

    _ensure_monitoring_order_status(order)

    snapshot = await _load_monitoring_snapshot(session, order_id)
    if snapshot is None:
        snapshot = await ensure_execution_monitoring_snapshot(
            session,
            order,
            source="monitoring_read_backfill",
        )
        await session.commit()
    else:
        metadata = dict(snapshot.extra_metadata or {})
        route_signature = _route_geometry_signature(order)
        stored_route_path = _normalize_route_path(metadata.get("route_path"))
        if (
            metadata.get("route_geometry_version") != _ROUTE_GEOMETRY_VERSION
            or metadata.get("route_signature") != route_signature
            or len(stored_route_path) < 2
        ):
            snapshot = await ensure_execution_monitoring_snapshot(
                session,
                order,
                source="monitoring_route_backfill",
            )
            await session.commit()

    database_alerts = [_serialize_alert(alert) for alert in await _load_open_monitoring_alerts(session, order_id)]
    merged_alerts = database_alerts + [alert for alert in snapshot.alerts if not any(alert.get("dedupe_key") == persisted.get("dedupe_key") for persisted in database_alerts)]

    metadata = dict(snapshot.extra_metadata or {})
    route_path = _normalize_route_path(metadata.get("route_path")) or _build_route_path(snapshot.route_points)
    current_position = metadata.get("current_position") or _current_position_for_progress_along_path(snapshot.route_points, route_path, snapshot.progress_percent)
    agent_update = metadata.get("agent_update") or _build_deterministic_agent_update(snapshot)

    snapshot_payload: dict[str, Any] = {
        "id": snapshot.id,
        "load_order_id": snapshot.load_order_id,
        "status": snapshot.status,
        "progress_percent": snapshot.progress_percent,
        "current_checkpoint": snapshot.current_checkpoint,
        "route_points": snapshot.route_points,
        "route_path": route_path,
        "current_position": current_position,
        "events": snapshot.events,
        "alerts": merged_alerts,
        "extra_metadata": metadata,
        "created_at": snapshot.created_at,
        "last_refreshed_at": snapshot.last_refreshed_at,
    }

    return ExecutionMonitoringReadModelResponse.model_validate(
        {
            "snapshot": snapshot_payload,
            "alerts": merged_alerts,
            "shipment": _build_shipment_summary(order, snapshot),
            "agent_update": agent_update,
        }
    )
