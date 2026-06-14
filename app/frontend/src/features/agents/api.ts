import { useAuth } from "@clerk/react";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../../lib/apiClient";
import type { DashboardLoadOrderSummary } from "../orders/api";

export type AgentKind = "orchestrator" | "ingestion" | "carrier_search" | "smart_comms" | "monitoring";

export type AgentActivityState = "running" | "completed" | "awaiting_operator" | "warning" | "error";

export type AgentStatus = {
  agent_kind: AgentKind;
  display_name: string;
  state: AgentActivityState;
  headline: string;
  last_activity_at: string | null;
  active_item_count: number;
};

export type AgentStatusListResponse = {
  agents: AgentStatus[];
};

export type OrchestratorTimelineItem = {
  agent: AgentKind;
  title: string;
  detail: string | null;
  next_action: string | null;
  load_order_id: string | null;
  customer_name: string | null;
  route_summary: string | null;
  order_status: string | null;
  created_at: string;
};

export function useAgentStatuses() {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["agents", "status"],
    queryFn: () => apiClient<AgentStatusListResponse>("/agents/status", getToken),
    refetchInterval: 30000,
  });
}

export function useDashboardLoadOrderSummary() {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["orders", "summary"],
    queryFn: () => apiClient<DashboardLoadOrderSummary>("/orders/summary", getToken),
    refetchInterval: 15000,
  });
}

export function useOrchestratorTimeline(limit = 20, loadOrderId?: string) {
  const { getToken } = useAuth();
  const searchParams = new URLSearchParams({ limit: String(limit) });
  if (loadOrderId) {
    searchParams.set("load_order_id", loadOrderId);
  }

  return useQuery({
    queryKey: ["agents", "orchestrator", "timeline", limit, loadOrderId],
    queryFn: () => apiClient<OrchestratorTimelineItem[]>(`/agents/orchestrator/timeline?${searchParams.toString()}`, getToken),
    refetchInterval: 15000,
  });
}
