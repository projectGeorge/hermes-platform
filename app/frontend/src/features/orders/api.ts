import { useAuth } from "@clerk/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../../lib/apiClient";


export type LoadOrder = {
  id: string;
  user_id: string;
  customer_id: string | null;
  customer_name: string | null;
  status: string;
  selected_trip_id: string | null;
  origin_id: string | null;
  origin_text: string | null;
  origin_load_date: string | null;
  destination_id: string | null;
  destination_text: string | null;
  destination_unload_date: string | null;
  distance_km: string | null;
  cargo_description: string | null;
  weight_kg: string | null;
  truck_type_id: number | null;
  adr_required: boolean;
  missing_fields: Record<string, unknown> | null;
  customer_price: string | null;
  currency: string;
  created_at: string;
  updated_at: string;
};

export type LoadOrderListPage = {
  items: LoadOrder[];
  total: number;
  skip: number;
  limit: number;
};

export type DashboardLoadOrderItem = {
  id: string;
  customer_name: string | null;
  status: string;
  origin_text: string | null;
  destination_text: string | null;
  updated_at: string;
};

export type DashboardLoadOrderSummary = {
  active_order_count: number;
  needs_attention_count: number;
  attention_orders: DashboardLoadOrderItem[];
  recent_active_orders: DashboardLoadOrderItem[];
};

export type LoadOrderMutationPayload = {
  customer_name?: string | null;
  origin_text?: string | null;
  origin_load_date?: string | null;
  destination_text?: string | null;
  destination_unload_date?: string | null;
  distance_km?: string | null;
  cargo_description?: string | null;
  weight_kg?: string | null;
  truck_type_id?: number | null;
  adr_required?: boolean;
  customer_price?: string | null;
  currency?: string | null;
};

export type TruckType = {
  id: number;
  name: string;
};

export type AgentActivity = {
  id: string;
  agent_kind: "orchestrator" | "ingestion" | "carrier_search" | "smart_comms" | "monitoring";
  activity_state: "running" | "completed" | "awaiting_operator" | "warning" | "error";
  load_order_id: string | null;
  title: string;
  detail: string | null;
  activity_key: string;
  next_action: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type DelegatedOrderAction =
  | "extract_email_into_order_draft"
  | "draft_message"
  | "open_shipment_monitoring"
  | "run_carrier_search";

export type ExecutionMonitoringRoutePoint = {
  kind: string;
  label: string;
  sequence: number;
  lat: number;
  lng: number;
  status: "pending" | "active" | "completed";
};

export type ExecutionMonitoringCoordinate = {
  lat: number;
  lng: number;
};

export type ExecutionMonitoringPosition = {
  label: string;
  lat: number;
  lng: number;
  progress_percent: number;
};

export type ExecutionMonitoringEvent = {
  event_type: string;
  title: string;
  detail: string | null;
  checkpoint_name: string | null;
  occurred_at: string;
  severity: "info" | "warning" | "critical";
};

export type MonitoringAlert = {
  id: string;
  load_order_id: string | null;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  status: "open" | "resolved";
  title: string;
  detail: string | null;
  dedupe_key: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
  resolved_at: string | null;
};

export type ExecutionMonitoringSnapshot = {
  id: string;
  load_order_id: string;
  status: "planned" | "in_transit" | "delayed" | "delivered";
  progress_percent: number;
  current_checkpoint: string | null;
  route_points: ExecutionMonitoringRoutePoint[];
  route_path: ExecutionMonitoringCoordinate[];
  current_position: ExecutionMonitoringPosition;
  events: ExecutionMonitoringEvent[];
  alerts: MonitoringAlert[];
  metadata: Record<string, unknown> | null;
  created_at: string;
  last_refreshed_at: string;
};

export type ExecutionMonitoringShipmentSummary = {
  route_label: string;
  customer_name: string | null;
  cargo_description: string | null;
  carrier_name: string | null;
  distance_km: number | null;
  current_status_label: string;
  last_update_source: string;
};

export type ExecutionMonitoringAgentUpdate = {
  source: "deterministic" | "cloud" | string;
  summary: string;
  operator_note: string | null;
  incident_summary: string | null;
  generated_at: string;
};

export type ExecutionMonitoringReadModel = {
  snapshot: ExecutionMonitoringSnapshot;
  alerts: MonitoringAlert[];
  shipment: ExecutionMonitoringShipmentSummary;
  agent_update: ExecutionMonitoringAgentUpdate;
};

export type LoadOrderIngestionResult = {
  ingestion_run_id: string;
  route: string;
  run_status: string;
  load_order: LoadOrder;
  extracted_payload: Record<string, unknown>;
  missing_fields: Record<string, string>;
  execution_path: string | null;
  provider: string | null;
  model_name: string | null;
  trace_steps: Array<Record<string, unknown>> | null;
};

export type SmartCommsConversation = {
  id: string;
  user_id: string;
  context_type: string;
  context_id: string | null;
  route_path: string;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export type DelegatedOrderActionResponse = {
  delegated_to: "ingestion" | "smart_comms" | "monitoring" | "carrier_search";
  activity: AgentActivity;
  ingestion_result: LoadOrderIngestionResult | null;
  smart_comms_conversation: SmartCommsConversation | null;
  monitoring_snapshot: ExecutionMonitoringReadModel | null;
};


const ORDERS_PAGE_SIZE = 500;


export async function listOrders(getToken: () => Promise<string | null>) {
  const orders: LoadOrder[] = [];
  let skip = 0;

  while (true) {
    const page = await apiClient<LoadOrder[]>(
      `/orders/?limit=${ORDERS_PAGE_SIZE}&skip=${skip}`,
      getToken,
    );
    orders.push(...page);

    if (page.length < ORDERS_PAGE_SIZE) {
      return orders;
    }

    skip += page.length;
  }
}

export function listOrdersPage(
  getToken: () => Promise<string | null>,
  params: {
    skip?: number;
    limit?: number;
    activeOnly?: boolean;
    search?: string;
  },
) {
  const searchParams = new URLSearchParams();

  searchParams.set("skip", String(params.skip ?? 0));
  searchParams.set("limit", String(params.limit ?? 20));

  if (params.activeOnly) {
    searchParams.set("active_only", "true");
  }

  const normalizedSearch = params.search?.trim();
  if (normalizedSearch) {
    searchParams.set("search", normalizedSearch);
  }

  return apiClient<LoadOrderListPage>(`/orders/page?${searchParams.toString()}`, getToken);
}

export function getDashboardLoadOrderSummary(
  getToken: () => Promise<string | null>,
  limit = 5,
) {
  return apiClient<DashboardLoadOrderSummary>(`/orders/summary?limit=${limit}`, getToken);
}

export function getOrder(orderId: string, getToken: () => Promise<string | null>) {
  return apiClient<LoadOrder>(`/orders/${orderId}`, getToken);
}

export function createOrder(
  getToken: () => Promise<string | null>,
  payload: LoadOrderMutationPayload,
) {
  return apiClient<LoadOrder>("/orders/", getToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateOrder(
  orderId: string,
  getToken: () => Promise<string | null>,
  payload: LoadOrderMutationPayload,
) {
  return apiClient<LoadOrder>(`/orders/${orderId}`, getToken, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function refreshOrderOrchestrator(orderId: string, getToken: () => Promise<string | null>) {
  return apiClient<AgentActivity>(`/orders/${orderId}/orchestrator-refresh`, getToken, {
    method: "POST",
  });
}

export function delegateOrderAction(
  getToken: () => Promise<string | null>,
  payload: {
    action: DelegatedOrderAction;
    load_order_id?: string;
    source_email_text?: string;
  },
) {
  return apiClient<DelegatedOrderActionResponse>("/orders/delegated-actions", getToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getExecutionMonitoring(
  orderId: string,
  getToken: () => Promise<string | null>,
) {
  return apiClient<ExecutionMonitoringReadModel>(`/monitoring/orders/${orderId}/execution`, getToken);
}

export function refreshExecutionMonitoring(
  orderId: string,
  getToken: () => Promise<string | null>,
) {
  return apiClient<ExecutionMonitoringReadModel>(`/monitoring/orders/${orderId}/refresh`, getToken, {
    method: "POST",
  });
}

export function formalizeOrder(orderId: string, getToken: () => Promise<string | null>) {
  return apiClient<LoadOrder>(`/orders/${orderId}/formalize`, getToken, {
    method: "POST",
  });
}

export function deleteOrder(orderId: string, getToken: () => Promise<string | null>) {
  return apiClient<void>(`/orders/${orderId}`, getToken, {
    method: "DELETE",
  });
}

export function cancelOrder(orderId: string, getToken: () => Promise<string | null>) {
  return apiClient<LoadOrder>(`/orders/${orderId}/cancel`, getToken, {
    method: "POST",
  });
}

export function listTruckTypes(getToken: () => Promise<string | null>) {
  return apiClient<TruckType[]>("/truck-types", getToken);
}

export function useRefreshOrderOrchestrator(orderId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => refreshOrderOrchestrator(orderId, getToken),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "status"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] }),
      ]);
    },
  });
}

export function useFormalizeOrder(orderId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => formalizeOrder(orderId, getToken),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", orderId, "carrier-candidates"] }),
        queryClient.invalidateQueries({ queryKey: ["monitoring", "execution", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "status"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] }),
      ]);
    },
  });
}

export function useDeleteOrder() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (orderId: string) => deleteOrder(orderId, getToken),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useCancelOrder() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (orderId: string) => cancelOrder(orderId, getToken),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
