import { apiClient } from "../../lib/apiClient";
import type { LoadOrder } from "../orders/api";


export type HumanValidationContext = {
  load_order: LoadOrder;
  latest_ingestion_run: {
    id: string;
    route: string;
    status: string;
    raw_text: string;
    extracted_payload: Record<string, unknown> | null;
    execution_path: string | null;
    provider: string | null;
    model_name: string | null;
    trace_steps: Array<Record<string, unknown>> | null;
  };
  missing_fields: Record<string, string>;
  blocked_missing_fields: Record<string, string>;
  reviewable_fields: string[];
  can_confirm_viability: boolean;
};

export type HumanValidationUpdatePayload = {
  customer_name?: string;
  destination_text?: string;
  origin_text?: string;
  origin_load_date?: string;
  destination_unload_date?: string;
  distance_km?: string;
  cargo_description?: string;
  weight_kg?: string;
  truck_type_id?: number;
  customer_price?: string;
  currency?: string;
  adr_required?: boolean;
  review_notes?: string;
};

export type HumanValidationConfirmPayload = {
  review_notes?: string;
};


export function getHumanValidationContext(
  orderId: string,
  getToken: () => Promise<string | null>,
) {
  return apiClient<HumanValidationContext>(`/orders/${orderId}/human-validation`, getToken);
}


export function updateHumanValidation(
  orderId: string,
  getToken: () => Promise<string | null>,
  payload: HumanValidationUpdatePayload,
) {
  return apiClient<HumanValidationContext>(`/orders/${orderId}/human-validation`, getToken, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}


export function confirmViability(
  orderId: string,
  getToken: () => Promise<string | null>,
  payload: HumanValidationConfirmPayload,
) {
  return apiClient<LoadOrder>(`/orders/${orderId}/confirm-viability`, getToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}


export function runCarrierSearch(
  orderId: string,
  getToken: () => Promise<string | null>,
) {
  return apiClient(`/orders/${orderId}/carrier-search`, getToken, {
    method: "POST",
  });
}


export function geocodeDistance(
  origin: string,
  destination: string,
  getToken: () => Promise<string | null>,
) {
  const params = new URLSearchParams({ origin, destination });
  return apiClient<{ distance_km: number }>(`/orders/geocode/distance?${params}`, getToken);
}
