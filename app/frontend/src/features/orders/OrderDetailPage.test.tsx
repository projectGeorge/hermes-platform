import type { ReactNode } from "react";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { routes } from "../../app/AppRouter";
import { AppProviders } from "../../app/providers/AppProviders";
import { queryClient } from "../../app/queryClient";

const getToken = vi.fn(async () => "session-token");

vi.mock("@clerk/react", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  SignIn: () => <div>Sign in</div>,
  SignUp: () => <div>Sign up</div>,
  UserButton: () => <button aria-label="User menu">User menu</button>,
  useAuth: () => ({ isLoaded: true, isSignedIn: true, getToken }),
}));

function buildOrder(overrides?: Record<string, unknown>) {
  return {
    id: "order-1",
    user_id: "11111111-1111-1111-1111-111111111111",
    customer_id: null,
    customer_name: "Acme Logistics",
    status: "viability_pending",
    selected_trip_id: "trip-42",
    origin_id: null,
    origin_text: "Madrid, ES",
    origin_load_date: "2026-05-04T09:30:00",
    destination_id: null,
    destination_text: "Paris, FR",
    destination_unload_date: "2026-05-05T12:00:00",
    distance_km: "1270.00",
    cargo_description: "Ceramic tiles",
    weight_kg: "7800.00",
    truck_type_id: 1,
    adr_required: false,
    missing_fields: null,
    customer_price: "1400.00",
    currency: "EUR",
    created_at: "2026-04-27T10:00:00",
    updated_at: "2026-04-27T10:05:00",
    ...overrides,
  };
}

function renderWithRoute(initialPath: string) {
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });

  return render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
}

describe("Order workflow hub", () => {
  afterEach(() => {
    cleanup();
    queryClient.clear();
    vi.unstubAllGlobals();
  });

  it("loads order detail and shows status, route, pricing, cargo, and workflow actions", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/users/me")) {
        return new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        );
      }

      if (url.endsWith("/orders/order-1")) {
        return new Response(JSON.stringify(buildOrder()), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/resolve")) {
        return new Response(JSON.stringify({ id: "conv-1", context_type: "load_order", context_id: "order-1", route_path: "/orders/order-1", title: null, user_id: "11111111-1111-1111-1111-111111111111", created_at: "2026-05-17T10:00:00Z", updated_at: "2026-05-17T10:00:00Z" }), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/conv-1/messages")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderWithRoute("/orders/order-1");

    expect(await screen.findByRole("heading", { name: /acme logistics/i })).toBeInTheDocument();
    expect(screen.getByText(/order workspace/i)).toBeInTheDocument();
    expect(screen.getAllByText(/viability pending/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/madrid, es/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/paris, fr/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/1400.00/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/ceramic tiles/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /edit order/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^intake/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /carrier match/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^monitoring/i })).not.toBeInTheDocument();
    expect(screen.getByText(/order workflow status is/i)).toBeInTheDocument();
    expect(screen.getByText(/carrier match unlocks after viability is confirmed/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /formalize order/i })).not.toBeInTheDocument();
  });

  it("shows clearer order-list row actions into detail", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/users/me")) {
        return new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        );
      }

      if (url.includes("/orders/summary")) {
        return new Response(JSON.stringify({
          active_order_count: 1,
          needs_attention_count: 1,
          attention_orders: [
            {
              id: "order-1",
              customer_name: "Acme Logistics",
              status: "viability_pending",
              origin_text: "Madrid, ES",
              destination_text: "Paris, FR",
              updated_at: "2026-05-17T10:00:00Z",
            },
          ],
          recent_active_orders: [
            {
              id: "order-1",
              customer_name: "Acme Logistics",
              status: "viability_pending",
              origin_text: "Madrid, ES",
              destination_text: "Paris, FR",
              updated_at: "2026-05-17T10:00:00Z",
            },
          ],
        }), { status: 200 });
      }

      if (url.includes("/orders/page?skip=0&limit=20")) {
        return new Response(JSON.stringify({
          items: [buildOrder()],
          total: 1,
          skip: 0,
          limit: 20,
        }), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderWithRoute("/orders");

    expect(await screen.findByRole("heading", { name: /orders/i })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /open detail/i })).toBeInTheDocument();
  });

  it("keeps dashboard linked to the main order workflow", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/users/me")) {
        return new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        );
      }

      if (url.includes("/orders/summary")) {
        return new Response(JSON.stringify({
          active_order_count: 1,
          needs_attention_count: 1,
          attention_orders: [
            {
              id: "order-1",
              customer_name: "Acme Logistics",
              status: "viability_pending",
              origin_text: "Madrid, ES",
              destination_text: "Paris, FR",
              updated_at: "2026-05-17T10:00:00Z",
            },
          ],
          recent_active_orders: [
            {
              id: "order-1",
              customer_name: "Acme Logistics",
              status: "viability_pending",
              origin_text: "Madrid, ES",
              destination_text: "Paris, FR",
              updated_at: "2026-05-17T10:00:00Z",
            },
          ],
        }), { status: 200 });
      }

      if (url.includes("/agents/status")) {
        return new Response(JSON.stringify({ agents: [] }), { status: 200 });
      }

      if (url.includes("/agents/orchestrator/timeline")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      if (url.includes("/monitoring/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/resolve")) {
        return new Response(JSON.stringify({ id: "conv-1", context_type: "dashboard", route_path: "/dashboard" }), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderWithRoute("/dashboard");

    expect(await screen.findByRole("heading", { name: /workflow timeline/i })).toBeInTheDocument();
  });

  it("shows the stronger dashboard workflow surface", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/users/me")) {
        return new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        );
      }

      if (url.includes("/orders/summary")) {
        return new Response(JSON.stringify({
          active_order_count: 1,
          needs_attention_count: 1,
          attention_orders: [
            {
              id: "order-1",
              customer_name: "Acme Logistics",
              status: "viability_pending",
              origin_text: "Madrid, ES",
              destination_text: "Paris, FR",
              updated_at: "2026-05-17T10:00:00Z",
            },
          ],
          recent_active_orders: [
            {
              id: "order-1",
              customer_name: "Acme Logistics",
              status: "viability_pending",
              origin_text: "Madrid, ES",
              destination_text: "Paris, FR",
              updated_at: "2026-05-17T10:00:00Z",
            },
          ],
        }), { status: 200 });
      }

      if (url.includes("/agents/status")) {
        return new Response(JSON.stringify({ agents: [] }), { status: 200 });
      }

      if (url.includes("/agents/orchestrator/timeline")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      if (url.includes("/monitoring/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/resolve")) {
        return new Response(JSON.stringify({ id: "conv-1", context_type: "dashboard", route_path: "/dashboard" }), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderWithRoute("/dashboard");

    expect(await screen.findByRole("heading", { name: /workflow timeline/i })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /review intake/i })).toBeInTheDocument();
  });

  it("shows search and active-order filtering on the orders list", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/users/me")) {
        return new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        );
      }

      if (url.includes("/orders/page?skip=0&limit=20")) {
        return new Response(JSON.stringify({
          items: [buildOrder()],
          total: 21,
          skip: 0,
          limit: 20,
        }), { status: 200 });
      }

      if (url.includes("/orders/page?skip=20&limit=20")) {
        return new Response(JSON.stringify({
          items: [buildOrder({ id: "order-2", customer_name: "Next page customer" })],
          total: 21,
          skip: 20,
          limit: 20,
        }), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderWithRoute("/orders");

    expect(await screen.findByRole("heading", { name: /orders/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search by order, client, or route/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /active orders/i })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /edit order/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /next/i })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: /next/i }));

    expect(await screen.findByText(/next page customer/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /previous/i })).toBeEnabled();
  });

  it("loads order detail and shows the stronger workflow hub summary", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/users/me")) {
        return new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        );
      }

      if (url.endsWith("/orders/order-1")) {
        return new Response(JSON.stringify(buildOrder()), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/resolve")) {
        return new Response(JSON.stringify({ id: "conv-1", context_type: "load_order", context_id: "order-1", route_path: "/orders/order-1", title: null, user_id: "11111111-1111-1111-1111-111111111111", created_at: "2026-05-17T10:00:00Z", updated_at: "2026-05-17T10:00:00Z" }), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/conv-1/messages")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderWithRoute("/orders/order-1");

    expect(await screen.findByRole("heading", { name: /acme logistics/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^workflow$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^workspaces$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to orders/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /edit order/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^intake/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /carrier match/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^monitoring/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delegate monitoring/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delegate drafting/i })).not.toBeInTheDocument();
    expect(screen.getByText(/shipment execution starts only after formalization and continues in monitoring/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /formalize order/i })).not.toBeInTheDocument();
    expect(screen.getByText(/carrier match unlocks after viability is confirmed/i)).toBeInTheDocument();
  });

  it("shows open monitoring only after order formalization", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/users/me")) {
        return new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        );
      }

      if (url.endsWith("/orders/order-2")) {
        return new Response(JSON.stringify(buildOrder({ id: "order-2", status: "formalized" })), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/resolve")) {
        return new Response(JSON.stringify({ id: "conv-2", context_type: "load_order", context_id: "order-2", route_path: "/orders/order-2", title: null, user_id: "11111111-1111-1111-1111-111111111111", created_at: "2026-05-17T10:00:00Z", updated_at: "2026-05-17T10:00:00Z" }), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/conv-2/messages")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderWithRoute("/orders/order-2");

    expect(await screen.findByRole("heading", { name: /acme logistics/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^monitoring/i })).toBeInTheDocument();
    expect(screen.getByText(/shipment execution starts only after formalization/i)).toBeInTheDocument();
  });

  it("allows formalizing a ready order from order detail", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.includes("/users/me")) {
        return new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        );
      }

      if (url.endsWith("/orders/order-3") && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify(buildOrder({ id: "order-3", status: "ready_for_formalization" })), { status: 200 });
      }

      if (url.endsWith("/orders/order-3/formalize") && init?.method === "POST") {
        return new Response(JSON.stringify(buildOrder({ id: "order-3", status: "formalized" })), { status: 200 });
      }

      if (url.includes("/agents/orchestrator/timeline")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderWithRoute("/orders/order-3");

    expect(await screen.findByRole("button", { name: /formalize order/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /formalize order/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/orders/order-3/formalize"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("shows carrier match link once viability is confirmed", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/users/me")) {
        return new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        );
      }

      if (url.endsWith("/orders/order-1")) {
        return new Response(JSON.stringify(buildOrder({ status: "viability_confirmed" })), { status: 200 });
      }

      if (url.includes("/agents/orchestrator/timeline")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderWithRoute("/orders/order-1");

    expect(await screen.findByRole("heading", { name: /acme logistics/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /carrier match/i })).toBeInTheDocument();
  });

});
