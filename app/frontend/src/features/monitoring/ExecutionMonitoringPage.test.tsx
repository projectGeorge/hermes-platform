import type { ReactNode } from "react";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppProviders } from "../../app/providers/AppProviders";
import { ExecutionMonitoringPage } from "./ExecutionMonitoringPage";


const getToken = vi.fn(async () => "session-token");


vi.mock("./RouteMap", () => ({
  RouteMap: ({ currentPosition }: { currentPosition: { progress_percent: number } }) => (
    <section aria-label="Route map" role="region">
      <p>{currentPosition.progress_percent}% complete</p>
    </section>
  ),
}));


vi.mock("@clerk/react", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  SignIn: () => <div>Sign in</div>,
  SignUp: () => <div>Sign up</div>,
  UserButton: () => <button>User</button>,
  useAuth: () => ({ isLoaded: true, isSignedIn: true, getToken }),
}));


function buildMonitoringPayload(overrides?: Record<string, unknown>) {
  return {
    snapshot: {
      id: "snapshot-1",
      load_order_id: "order-1",
      status: "delayed",
      progress_percent: 58,
      current_checkpoint: "FR/ES border",
      route_points: [
        { kind: "origin", label: "Madrid, ES", sequence: 0, lat: 40.4168, lng: -3.7038, status: "completed" },
        { kind: "linehaul", label: "Linehaul corridor (634 km)", sequence: 1, lat: 43.7795, lng: -1.1609, status: "completed" },
        { kind: "border", label: "ES/FR border", sequence: 2, lat: 46.2217, lng: 0.4089, status: "active" },
        { kind: "destination", label: "Paris, FR", sequence: 3, lat: 48.8566, lng: 2.3522, status: "pending" },
      ],
      route_path: [
        { lat: 40.4168, lng: -3.7038 },
        { lat: 43.7795, lng: -1.1609 },
        { lat: 46.2217, lng: 0.4089 },
        { lat: 48.8566, lng: 2.3522 },
      ],
      current_position: {
        label: "Approaching ES/FR border",
        lat: 45.5811,
        lng: -0.0142,
        progress_percent: 58,
      },
      events: [
        {
          event_type: "pickup_completed",
          title: "Pickup completed",
          detail: "Shipment was released from origin handling and assigned to the route.",
          checkpoint_name: "Madrid, ES",
          occurred_at: "2026-05-18T08:20:00Z",
          severity: "info",
        },
        {
          event_type: "border_delay_detected",
          title: "Border delay detected",
          detail: "Traffic controls extended checkpoint handling by 45 minutes.",
          checkpoint_name: "FR/ES border",
          occurred_at: "2026-05-18T14:05:00Z",
          severity: "warning",
        },
      ],
      alerts: [
        {
          id: "execution-1-border-delay-detected",
          load_order_id: "order-1",
          alert_type: "execution_incident",
          severity: "warning",
          status: "open",
          title: "Border delay detected",
          detail: "Traffic controls extended checkpoint handling by 45 minutes.",
          dedupe_key: "execution_incident:order-1:border_delay_detected",
          metadata: { source: "simulation" },
          created_at: "2026-05-18T14:05:00Z",
          resolved_at: null,
        },
      ],
      metadata: {
        route_label: "Madrid, ES -> Paris, FR",
        refresh_count: 1,
      },
      created_at: "2026-05-18T08:00:00Z",
      last_refreshed_at: "2026-05-18T14:05:00Z",
    },
    alerts: [
      {
        id: "execution-1-border-delay-detected",
        load_order_id: "order-1",
        alert_type: "execution_incident",
        severity: "warning",
        status: "open",
        title: "Border delay detected",
        detail: "Traffic controls extended checkpoint handling by 45 minutes.",
        dedupe_key: "execution_incident:order-1:border_delay_detected",
        metadata: { source: "simulation" },
        created_at: "2026-05-18T14:05:00Z",
        resolved_at: null,
      },
    ],
    shipment: {
      route_label: "Madrid, ES -> Paris, FR",
      customer_name: "Acme Logistics",
      cargo_description: "Ceramic tiles",
      carrier_name: "Blue Line Cargo",
      distance_km: 1270,
      current_status_label: "Delayed",
      last_update_source: "operator_refresh",
    },
    agent_update: {
      source: "cloud",
      summary: "Shipment remains in transit near the border checkpoint with a bounded delay signal.",
      operator_note: "No escalation yet. Check again after the border leg clears.",
      incident_summary: "Traffic controls extended checkpoint handling by 45 minutes.",
      generated_at: "2026-05-18T14:05:00Z",
    },
    ...overrides,
  };
}


function renderPage() {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={["/orders/order-1/monitoring"]}>
        <Routes>
          <Route path="/orders/:orderId/monitoring" element={<ExecutionMonitoringPage />} />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
}


describe("ExecutionMonitoringPage", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders persisted shipment monitoring state with route, incidents, and agent update", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/monitoring/orders/order-1/execution")) {
        return new Response(JSON.stringify(buildMonitoringPayload()), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByRole("heading", { name: /madrid, es -> paris, fr/i })).toBeInTheDocument();
    expect(screen.getByText(/execution monitoring/i)).toBeInTheDocument();
    expect(screen.getByText(/blue line cargo/i)).toBeInTheDocument();
    expect(screen.getByText(/shipment remains in transit near the border checkpoint/i)).toBeInTheDocument();
    expect(screen.getAllByText(/border delay detected/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/pickup completed/i)).toBeInTheDocument();
    expect(screen.getByText(/approaching es\/fr border/i)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /route map/i })).toBeInTheDocument();
  });

  it("refreshes monitoring and shows updated persisted progress", async () => {
    let refreshCount = 0;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.includes("/monitoring/orders/order-1/execution") && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify(buildMonitoringPayload()), { status: 200 });
      }

      if (url.includes("/monitoring/orders/order-1/refresh") && init?.method === "POST") {
        refreshCount += 1;
        return new Response(
          JSON.stringify(
            buildMonitoringPayload({
              snapshot: {
                ...buildMonitoringPayload().snapshot,
                progress_percent: 81,
                status: "in_transit",
                current_checkpoint: "Paris, FR",
                current_position: {
                  label: "Approaching Paris, FR",
                  lat: 47.9122,
                  lng: 1.6022,
                  progress_percent: 81,
                },
                events: [
                  ...buildMonitoringPayload().snapshot.events,
                  {
                    event_type: "resumed_movement",
                    title: "Resumed movement",
                    detail: "Shipment cleared the monitored bottleneck and returned to scheduled pace.",
                    checkpoint_name: "ES/FR border",
                    occurred_at: "2026-05-18T16:00:00Z",
                    severity: "info",
                  },
                ],
                alerts: [],
                last_refreshed_at: "2026-05-18T16:00:00Z",
              },
              alerts: [],
              shipment: {
                ...buildMonitoringPayload().shipment,
                current_status_label: "In Transit",
                last_update_source: "operator_refresh",
              },
              agent_update: {
                source: "deterministic",
                summary: "Shipment cleared the delay zone and is advancing toward the final delivery leg.",
                operator_note: "Refresh again near arrival for delivery confirmation.",
                incident_summary: null,
                generated_at: "2026-05-18T16:00:00Z",
              },
            }),
          ),
          { status: 200 },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByRole("heading", { name: /madrid, es -> paris, fr/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /refresh monitoring/i }));

    expect(await screen.findByText(/shipment cleared the delay zone and is advancing toward the final delivery leg/i)).toBeInTheDocument();
    expect(screen.getByText(/approaching paris, fr/i)).toBeInTheDocument();
    expect(screen.getAllByText(/81%/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/no active incidents\./i)).toBeInTheDocument();

    await waitFor(() => {
      expect(refreshCount).toBe(1);
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/monitoring/orders/order-1/refresh"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
