import { useEffect } from "react";
import type { DivIcon, LatLngExpression, Map as LeafletMap } from "leaflet";
import L from "leaflet";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, useMap } from "react-leaflet";

import type {
  ExecutionMonitoringCoordinate,
  ExecutionMonitoringPosition,
  ExecutionMonitoringRoutePoint,
} from "../orders/api";


type RouteMapProps = {
  routePath: ExecutionMonitoringCoordinate[];
  routePoints: ExecutionMonitoringRoutePoint[];
  currentPosition: ExecutionMonitoringPosition;
  className?: string;
};


function checkpointTone(status: ExecutionMonitoringRoutePoint["status"]) {
  if (status === "completed") {
    return { fillColor: "#6ed4a0", color: "#d9fff0" };
  }
  if (status === "active") {
    return { fillColor: "#818cf8", color: "#f2f7fb" };
  }
  return { fillColor: "#334155", color: "#cbd5e1" };
}


function buildTileLayerConfig() {
  const provider = (import.meta.env.VITE_MONITORING_TILE_PROVIDER ?? "maptiler").trim().toLowerCase();
  const mapTilerKey = import.meta.env.VITE_MAPTILER_API_KEY?.trim() ?? "";
  const mapStyle = import.meta.env.VITE_MAPTILER_STYLE?.trim() || "streets-v2";

  if (provider === "maptiler" && mapTilerKey) {
    return {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://www.maptiler.com/copyright/">MapTiler</a>',
      url: `https://api.maptiler.com/maps/${mapStyle}/{z}/{x}/{y}.png?key=${mapTilerKey}`,
    };
  }

  return {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  };
}


function buildTruckIcon(): DivIcon {
  return L.divIcon({
    className: "hermes-truck-marker",
    html: `
      <div class="hermes-truck-marker__inner" aria-hidden="true">
        <svg width="42" height="42" viewBox="0 0 42 42" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="21" cy="21" r="18" fill="rgba(129,140,248,0.18)" stroke="rgba(129,140,248,0.42)" stroke-width="1.4" />
          <path d="M11 23.4V16.8C11 15.9163 11.7163 15.2 12.6 15.2H24.6C25.4837 15.2 26.2 15.9163 26.2 16.8V18.6H29.2059C29.7333 18.6 30.2243 18.8661 30.5119 19.3079L32.706 22.6791C32.8767 22.9414 32.9677 23.2474 32.9677 23.5603V27.2C32.9677 28.0837 32.2514 28.8 31.3677 28.8H30.2C30.2 30.4569 28.8569 31.8 27.2 31.8C25.5431 31.8 24.2 30.4569 24.2 28.8H18.8C18.8 30.4569 17.4569 31.8 15.8 31.8C14.1431 31.8 12.8 30.4569 12.8 28.8H12.6C11.7163 28.8 11 28.0837 11 27.2V23.4Z" fill="#F2F7FB" stroke="#818cf8" stroke-width="1.2" stroke-linejoin="round" />
          <circle cx="15.8" cy="28.8" r="2.1" fill="#071017" stroke="#818cf8" stroke-width="1.1" />
          <circle cx="27.2" cy="28.8" r="2.1" fill="#071017" stroke="#818cf8" stroke-width="1.1" />
          <path d="M26.2 20.2H29.1L30.9 23H26.2V20.2Z" fill="#818cf8" fill-opacity="0.3" />
        </svg>
      </div>
    `,
    iconAnchor: [21, 21],
    iconSize: [42, 42],
  });
}


function FitMapBounds({ points }: { points: LatLngExpression[] }) {
  const map = useMap();

  useEffect(() => {
    if (points.length === 0) {
      return;
    }

    if (points.length === 1) {
      map.setView(points[0], 7);
      return;
    }

    map.fitBounds(L.latLngBounds(points), {
      padding: [28, 28],
      maxZoom: 8,
    });
  }, [map, points]);

  return null;
}


function InvalidateMapSize() {
  const map = useMap();

  useEffect(() => {
    const timer = window.setTimeout(() => {
      map.invalidateSize();
    }, 0);

    return () => {
      window.clearTimeout(timer);
    };
  }, [map]);

  return null;
}


function routeMapCenter(routePath: ExecutionMonitoringCoordinate[], currentPosition: ExecutionMonitoringPosition): LatLngExpression {
  if (routePath.length > 0) {
    return [routePath[0].lat, routePath[0].lng];
  }
  return [currentPosition.lat, currentPosition.lng];
}


export function RouteMap({ routePath, routePoints, currentPosition, className }: RouteMapProps) {
  const safePath = routePath.length > 1 ? routePath : routePoints.map((point) => ({ lat: point.lat, lng: point.lng }));
  const polylinePositions = safePath.map((point) => [point.lat, point.lng] as LatLngExpression);
  const checkpointPositions = routePoints.map((point) => [point.lat, point.lng] as LatLngExpression);
  const boundsPoints = [...polylinePositions, [currentPosition.lat, currentPosition.lng] as LatLngExpression];
  const tileLayer = buildTileLayerConfig();
  const truckIcon = buildTruckIcon();

  return (
    <div
      aria-label="Route map"
      className={`overflow-hidden rounded-xl border border-white/8 bg-[#06131b] ${className ?? ""}`}
      role="region"
    >
      <MapContainer
        center={routeMapCenter(safePath, currentPosition)}
        className="h-full w-full"
        scrollWheelZoom={false}
        zoom={5}
      >
        <TileLayer attribution={tileLayer.attribution} url={tileLayer.url} />
        <Polyline pathOptions={{ color: "#818cf8", lineCap: "round", lineJoin: "round", opacity: 0.9, weight: 5 }} positions={polylinePositions} />
        {routePoints.map((point, index) => {
          const tone = checkpointTone(point.status);

          return (
            <CircleMarker
              center={checkpointPositions[index]}
              key={`${point.kind}-${point.sequence}`}
              pathOptions={{ color: tone.color, fillColor: tone.fillColor, fillOpacity: 1, opacity: 1, weight: 2 }}
              radius={6}
            />
          );
        })}
        <Marker icon={truckIcon} position={[currentPosition.lat, currentPosition.lng]} />
        <FitMapBounds points={boundsPoints} />
        <InvalidateMapSize />
      </MapContainer>
    </div>
  );
}


export function fitRouteMapBounds(map: LeafletMap, points: LatLngExpression[]) {
  if (points.length === 0) {
    return;
  }

  if (points.length === 1) {
    map.setView(points[0], 7);
    return;
  }

  map.fitBounds(L.latLngBounds(points), {
    padding: [28, 28],
    maxZoom: 8,
  });
}
