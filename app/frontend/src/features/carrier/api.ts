import { apiClient } from "../../lib/apiClient";
import type { LoadOrder } from "../orders/api";


export type CarrierCandidate = {
  trip_id: string;
  carrier_id: string;
  company_name: string;
  truck_type_id: number | null;
  reliability_rating: string | null;
  documentation_valid: boolean;
  adr_capable: boolean;
  base_price_km: string | null;
  carrier_price: string | null;
  profit_margin: string | null;
  proposal_status: "candidate" | "rejected";
  ai_rejection_reason:
    | "invalid_documentation"
    | "adr_not_supported"
    | "truck_type_mismatch"
    | "non_profitable"
    | null;
  is_selected: boolean;
  ranking_score: string | null;
  score_breakdown: Record<string, number> | null;
  agent_reasoning: string | null;
};

export type CarrierSearchSnapshot = {
  load_order: LoadOrder;
  candidates: CarrierCandidate[];
};


export function runCarrierSearch(
  orderId: string,
  getToken: () => Promise<string | null>,
) {
  return apiClient<CarrierSearchSnapshot>(`/orders/${orderId}/carrier-search`, getToken, {
    method: "POST",
  });
}


export function getCarrierCandidates(
  orderId: string,
  getToken: () => Promise<string | null>,
) {
  return apiClient<CarrierSearchSnapshot>(`/orders/${orderId}/carrier-candidates`, getToken);
}


export function selectCarrier(
  orderId: string,
  getToken: () => Promise<string | null>,
  payload: { trip_id: string | null },
) {
  return apiClient<CarrierSearchSnapshot>(`/orders/${orderId}/carrier-selection`, getToken, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}
