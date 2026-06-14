import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import React from "react";
import { DashboardPage } from "./DashboardPage";

vi.mock("@clerk/react", () => ({
  useAuth: () => ({ getToken: async () => "mock-token" }),
  useUser: () => ({ user: null }),
}));


function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}


function renderDashboard() {
  const queryClient = createQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}


describe("DashboardPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("shows a broader workflow label on the timeline surface instead of Orchestrator only", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const urlStr = String(url);
        if (urlStr.includes("/orders/summary")) {
          return new Response(
            JSON.stringify({
              active_order_count: 2,
              needs_attention_count: 1,
              attention_orders: [
                {
                  id: "order-1",
                  customer_name: "Acme",
                  status: "viability_pending",
                  origin_text: "Madrid, ES",
                  destination_text: "Paris, FR",
                  updated_at: "2025-01-01T00:00:00Z",
                },
              ],
              recent_active_orders: [
                {
                  id: "order-2",
                  customer_name: "Beta",
                  status: "formalized",
                  origin_text: "Porto, PT",
                  destination_text: "Lyon, FR",
                  updated_at: "2025-01-01T00:00:00Z",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (urlStr.includes("/agents/status")) {
          return new Response(
            JSON.stringify({
              agents: [
                { agent_kind: "orchestrator", display_name: "Orchestrator", state: "completed", headline: "Order received", last_activity_at: "2025-01-01T00:00:00Z", active_item_count: 0, open_alert_count: 0 },
                { agent_kind: "ingestion", display_name: "Ingestion", state: "completed", headline: "No ingestion runs", last_activity_at: null, active_item_count: 0 },
                { agent_kind: "carrier_search", display_name: "Carrier Search", state: "completed", headline: "No searches performed", last_activity_at: null, active_item_count: 0 },
                { agent_kind: "smart_comms", display_name: "Smart Comms", state: "completed", headline: "No conversations", last_activity_at: null, active_item_count: 0 },
                { agent_kind: "monitoring", display_name: "Monitoring", state: "completed", headline: "Shipment monitoring available", last_activity_at: null, active_item_count: 0 },
              ],
            }),
            { status: 200 },
          );
        }
        if (urlStr.includes("/agents/orchestrator/timeline")) {
          return new Response(
            JSON.stringify([
              { agent: "orchestrator", title: "Order created", detail: null, next_action: "Run ingestion", load_order_id: null, customer_name: "Acme", route_summary: null, order_status: "viability_pending", created_at: "2025-01-01T00:00:00Z" },
              { agent: "ingestion", title: "Extraction finished", detail: null, next_action: null, load_order_id: null, customer_name: "Acme", route_summary: null, order_status: "viability_pending", created_at: "2025-01-01T00:00:01Z" },
            ]),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );

    renderDashboard();

    expect(await screen.findByText("Agent")).toBeTruthy();
    expect(screen.getByText("Ingestion")).toBeTruthy();
    expect(screen.getByText("Next: Run ingestion")).toBeTruthy();
  });

  it("maps raw agent states to simplified operator-facing labels", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const urlStr = String(url);
        if (urlStr.includes("/orders/summary")) {
          return new Response(
            JSON.stringify({
              active_order_count: 1,
              needs_attention_count: 0,
              attention_orders: [],
              recent_active_orders: [
                {
                  id: "order-1",
                  customer_name: "Acme",
                  status: "formalized",
                  origin_text: "Madrid, ES",
                  destination_text: "Paris, FR",
                  updated_at: "2025-01-01T00:00:00Z",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (urlStr.includes("/agents/status")) {
          return new Response(
            JSON.stringify({
              agents: [
                { agent_kind: "orchestrator", display_name: "Orchestrator", state: "running", headline: "Processing", last_activity_at: "2025-01-01T00:00:00Z", active_item_count: 1, open_alert_count: 0 },
                { agent_kind: "ingestion", display_name: "Ingestion", state: "awaiting_operator", headline: "Review needed", last_activity_at: "2025-01-01T00:00:00Z", active_item_count: 0 },
                { agent_kind: "carrier_search", display_name: "Carrier Search", state: "completed", headline: "Idle", last_activity_at: null, active_item_count: 0 },
                { agent_kind: "smart_comms", display_name: "Smart Comms", state: "completed", headline: "Idle", last_activity_at: null, active_item_count: 0 },
                { agent_kind: "monitoring", display_name: "Monitoring", state: "completed", headline: "Shipment monitoring available", last_activity_at: null, active_item_count: 0 },
              ],
            }),
            { status: 200 },
          );
        }
        if (urlStr.includes("/agents/orchestrator/timeline")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    renderDashboard();

    expect(await screen.findByText("Working")).toBeTruthy();
    expect(screen.getByText("Needs operator")).toBeTruthy();
  });
});
