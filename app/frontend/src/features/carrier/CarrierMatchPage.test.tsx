import type { ReactNode } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CarrierMatchPage } from "./CarrierMatchPage";


const getToken = vi.fn(async () => "session-token");


vi.mock("@clerk/react", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  SignIn: () => <div>Sign in</div>,
  SignUp: () => <div>Sign up</div>,
  UserButton: () => <button>User</button>,
  useAuth: () => ({ isLoaded: true, isSignedIn: true, getToken }),
}));


function renderCarrierMatchPage(queryClient?: QueryClient) {
  const client = queryClient ??
    new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
        mutations: {
          retry: false,
        },
      },
    });

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/orders/order-1/carrier-match"]}>
        <Routes>
          <Route path="/orders/:orderId/carrier-match" element={<CarrierMatchPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}


function buildSnapshot(selectedTripId: string | null = null) {
  return {
    load_order: {
      id: "order-1",
      user_id: "11111111-1111-1111-1111-111111111111",
      customer_id: null,
      customer_name: "Acme Logistics",
      status: selectedTripId ? "ready_for_formalization" : "searching_carrier",
      selected_trip_id: selectedTripId,
      origin_id: null,
      origin_text: "Madrid, ES",
      origin_load_date: null,
      destination_id: null,
      destination_text: "Paris, FR",
      destination_unload_date: null,
      distance_km: "1270.00",
      cargo_description: "Ceramic tiles",
      weight_kg: "7800.00",
      truck_type_id: 1,
      adr_required: false,
      missing_fields: null,
      customer_price: "1400.00",
      currency: "EUR",
      created_at: "2026-04-30T10:00:00Z",
      updated_at: "2026-04-30T10:00:00Z",
    },
    candidates: [
      {
        trip_id: "trip-1",
        carrier_id: "carrier-1",
        company_name: "Atlas Freight",
        truck_type_id: 1,
        reliability_rating: "4.8",
        documentation_valid: true,
        adr_capable: true,
        base_price_km: "0.95",
        carrier_price: "1200.00",
        profit_margin: "200.00",
        proposal_status: "candidate",
        ai_rejection_reason: null,
        is_selected: selectedTripId === "trip-1",
      },
      {
        trip_id: "trip-2",
        carrier_id: "carrier-2",
        company_name: "Broken Docs Logistics",
        truck_type_id: 1,
        reliability_rating: "3.2",
        documentation_valid: false,
        adr_capable: true,
        base_price_km: "1.20",
        carrier_price: "1520.00",
        profit_margin: "-120.00",
        proposal_status: "rejected",
        ai_rejection_reason: "invalid_documentation",
        is_selected: false,
      },
    ],
  };
}


describe("CarrierMatchPage", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders an existing persisted carrier snapshot on first load", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/orders/order-1/carrier-candidates")) {
        return new Response(JSON.stringify(buildSnapshot("trip-1")), { status: 200 });
      }

      if (url.includes("/truck-types")) {
        return new Response(JSON.stringify([{ id: 1, name: "Box truck" }]), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderCarrierMatchPage();

    expect(await screen.findByRole("heading", { name: /carrier match/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /atlas freight/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^selected carrier$/i })).toBeInTheDocument();
    expect(screen.getByText(/ready to formalize/i)).toBeInTheDocument();
    expect(screen.getByText(/snapshot ready/i)).toBeInTheDocument();
  });

  it("loads the persisted snapshot, runs carrier search when missing, and selects a candidate", async () => {
    let currentSnapshot: ReturnType<typeof buildSnapshot> | null = null;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/orders/order-1/carrier-candidates") && method === "GET") {
        if (!currentSnapshot) {
          return new Response(
            JSON.stringify({ detail: "Load order has no carrier-search snapshot" }),
            { status: 404 },
          );
        }

        return new Response(JSON.stringify(currentSnapshot), { status: 200 });
      }

      if (url.endsWith("/orders/order-1") && method === "GET") {
        return new Response(
          JSON.stringify({
            ...buildSnapshot().load_order,
            status: "viability_confirmed",
            selected_trip_id: null,
          }),
          { status: 200 },
        );
      }

      if (url.includes("/orders/order-1/carrier-search") && method === "POST") {
        currentSnapshot = buildSnapshot();
        return new Response(JSON.stringify(currentSnapshot), { status: 201 });
      }

      if (url.includes("/orders/order-1/carrier-selection") && method === "PUT") {
        expect(JSON.parse(String(init?.body))).toEqual({ trip_id: "trip-1" });
        currentSnapshot = buildSnapshot("trip-1");
        return new Response(JSON.stringify(currentSnapshot), { status: 200 });
      }

      if (url.includes("/truck-types") && method === "GET") {
        return new Response(JSON.stringify([{ id: 1, name: "Box truck" }]), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url} ${method}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderCarrierMatchPage();

    expect(await screen.findByText(/no carrier search has been run for this order yet/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url, init]) =>
        String(url).includes("/orders/order-1/carrier-search")
        && (init as RequestInit | undefined)?.method === "POST")).toBe(true);
    });

    const user = userEvent.setup();
    await screen.findByRole("heading", { name: /atlas freight/i });

    expect(screen.getByRole("heading", { name: /^selected carrier$/i })).toBeInTheDocument();
    expect(screen.getByText(/searching carrier/i)).toBeInTheDocument();
    expect(screen.getByText(/no carrier selected/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^select$/i })).toBeInTheDocument();
    expect(screen.queryByText(/broken docs logistics/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^select$/i }));

    await waitFor(() => {
      expect(screen.getByText(/ready to formalize/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/^selected$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^deselect$/i })).toBeInTheDocument();
  });

  it("auto-runs carrier search when entering from viability confirmed without a snapshot", async () => {
    let currentSnapshot: ReturnType<typeof buildSnapshot> | null = null;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/orders/order-1/carrier-candidates") && method === "GET") {
        if (!currentSnapshot) {
          return new Response(
            JSON.stringify({ detail: "Load order has no carrier-search snapshot" }),
            { status: 404 },
          );
        }

        return new Response(JSON.stringify(currentSnapshot), { status: 200 });
      }

      if (url.endsWith("/orders/order-1") && method === "GET") {
        return new Response(
          JSON.stringify({
            ...buildSnapshot().load_order,
            status: "viability_confirmed",
            selected_trip_id: null,
          }),
          { status: 200 },
        );
      }

      if (url.includes("/orders/order-1/carrier-search") && method === "POST") {
        currentSnapshot = buildSnapshot();
        return new Response(JSON.stringify(currentSnapshot), { status: 201 });
      }

      if (url.includes("/truck-types") && method === "GET") {
        return new Response(JSON.stringify([{ id: 1, name: "Box truck" }]), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url} ${method}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderCarrierMatchPage();

    expect(await screen.findByText(/no carrier search has been run for this order yet/i)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /atlas freight/i })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/orders/order-1/carrier-search"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows a fatal error when the carrier snapshot request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500 })),
    );

    renderCarrierMatchPage();

    expect(await screen.findByText(/failed to load carrier match/i)).toBeInTheDocument();
  });

  it("does not offer carrier search before viability is confirmed", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/orders/order-1/carrier-candidates") && method === "GET") {
        return new Response(
          JSON.stringify({ detail: "Load order has no carrier-search snapshot" }),
          { status: 404 },
        );
      }

      if (url.endsWith("/orders/order-1") && method === "GET") {
        return new Response(
          JSON.stringify({
            ...buildSnapshot().load_order,
            status: "viability_pending",
            selected_trip_id: null,
          }),
          { status: 200 },
        );
      }

      if (url.includes("/truck-types") && method === "GET") {
        return new Response(JSON.stringify([{ id: 1, name: "Box truck" }]), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url} ${method}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderCarrierMatchPage();

    expect(await screen.findByText(/carrier search is not available yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run carrier search/i })).not.toBeInTheDocument();
    expect(screen.getByText(/current order status: viability pending/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to order/i })).toBeInTheDocument();
  });
});
