import type { ReactNode } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrderFormPage } from "./OrderFormPage";

const navigateMock = vi.fn();
const getToken = vi.fn(async () => "session-token");

vi.mock("@clerk/react", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  SignIn: () => <div>Sign in</div>,
  SignUp: () => <div>Sign up</div>,
  UserButton: () => <button>User</button>,
  useAuth: () => ({ isLoaded: true, isSignedIn: true, getToken }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");

  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

function renderOrderFormPage(mode: "create" | "edit") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  const initialEntry = mode === "create" ? "/orders/new" : "/orders/order-1/edit";

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/orders/new" element={<OrderFormPage mode={mode} />} />
          <Route path="/orders/:orderId/edit" element={<OrderFormPage mode={mode} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function buildOrder(overrides?: Record<string, unknown>) {
  return {
    id: "order-1",
    user_id: "11111111-1111-1111-1111-111111111111",
    customer_id: null,
    customer_name: "Acme Logistics",
    status: "viability_pending",
    selected_trip_id: null,
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

describe("OrderFormPage", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    navigateMock.mockReset();
  });

  it("create mode loads truck types and then submits create payload", async () => {
    let createPayload: Record<string, unknown> | null = null;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/truck-types")) {
        return new Response(
          JSON.stringify([
            { id: 1, name: "mega" },
            { id: 2, name: "refrigerated" },
          ]),
          { status: 200 },
        );
      }

      if (url.includes("/smart-comms/conversations/resolve")) {
        return new Response(JSON.stringify({
          id: "conv-1",
          user_id: "11111111-1111-1111-1111-111111111111",
          context_type: "dashboard",
          context_id: null,
          route_path: "/orders/new",
          title: null,
          created_at: "2026-05-17T10:00:00Z",
          updated_at: "2026-05-17T10:00:00Z",
        }), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/conv-1/messages")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      if (url.endsWith("/orders/") && method === "POST") {
        createPayload = JSON.parse(String(init?.body));

        return new Response(JSON.stringify(buildOrder({ id: "order-created", truck_type_id: 2, adr_required: true })), {
          status: 201,
        });
      }

      throw new Error(`Unexpected request: ${url} ${method}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderOrderFormPage("create");

    expect(await screen.findByRole("heading", { name: /create order/i })).toBeInTheDocument();
    expect(screen.getByText(/manual order entry/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/customer name/i), { target: { value: "Acme Logistics" } });
    fireEvent.change(screen.getByPlaceholderText("Madrid, ES"), { target: { value: "Madrid, ES" } });
    fireEvent.change(screen.getByLabelText(/origin load date/i), { target: { value: "2026-05-04T09:30" } });
    fireEvent.change(screen.getByPlaceholderText("Paris, FR"), { target: { value: "Paris, FR" } });
    fireEvent.change(screen.getByLabelText(/destination unload date/i), { target: { value: "2026-05-05T12:00" } });
    fireEvent.change(screen.getByLabelText(/distance \(km\)/i), { target: { value: "1270.00" } });
    fireEvent.change(screen.getByLabelText(/cargo description/i), { target: { value: "Ceramic tiles" } });
    fireEvent.change(screen.getByLabelText(/weight \(kg\)/i), { target: { value: "7800.00" } });
    fireEvent.change(screen.getByLabelText(/truck type/i), { target: { value: "2" } });
    fireEvent.click(screen.getByLabelText(/adr required/i));
    fireEvent.change(screen.getByLabelText(/customer price/i), { target: { value: "1400.00" } });
    fireEvent.change(screen.getByLabelText(/currency/i), { target: { value: "EUR" } });

    fireEvent.click(screen.getByRole("button", { name: /save order/i }));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/orders/order-created");
    });
    expect(createPayload).toMatchObject({
      customer_name: "Acme Logistics",
      origin_text: "Madrid, ES",
      destination_text: "Paris, FR",
      cargo_description: "Ceramic tiles",
      truck_type_id: 2,
      adr_required: true,
      customer_price: "1400.00",
      currency: "EUR",
    });
  });

  it("edit mode loads existing order and submits update payload", async () => {
    let updatePayload: Record<string, unknown> | null = null;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/truck-types")) {
        return new Response(
          JSON.stringify([
            { id: 1, name: "mega" },
            { id: 2, name: "refrigerated" },
          ]),
          { status: 200 },
        );
      }

      if (url.includes("/smart-comms/conversations/resolve")) {
        return new Response(JSON.stringify({
          id: "conv-1",
          user_id: "11111111-1111-1111-1111-111111111111",
          context_type: "load_order",
          context_id: "order-1",
          route_path: "/orders/order-1/edit",
          title: null,
          created_at: "2026-05-17T10:00:00Z",
          updated_at: "2026-05-17T10:00:00Z",
        }), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/conv-1/messages")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      if (url.endsWith("/orders/order-1") && method === "GET") {
        return new Response(JSON.stringify(buildOrder()), { status: 200 });
      }

      if (url.endsWith("/orders/order-1") && method === "PUT") {
        updatePayload = JSON.parse(String(init?.body));

        return new Response(
          JSON.stringify(buildOrder({ customer_name: "Updated customer", cargo_description: "Updated cargo" })),
          { status: 200 },
        );
      }

      throw new Error(`Unexpected request: ${url} ${method}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderOrderFormPage("edit");

    expect(await screen.findByRole("heading", { name: /edit order/i })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Acme Logistics")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/customer name/i), { target: { value: "Updated customer" } });
    fireEvent.change(screen.getByLabelText(/cargo description/i), { target: { value: "Updated cargo" } });
    fireEvent.click(screen.getByRole("button", { name: /save order/i }));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/orders/order-1");
    });
    expect(updatePayload).toMatchObject({
      customer_name: "Updated customer",
      cargo_description: "Updated cargo",
    });
  });

  it("create mode renders the upgraded order workspace framing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);

        if (url.includes("/truck-types")) {
          return new Response(
            JSON.stringify([{ id: 1, name: "mega" }, { id: 2, name: "refrigerated" }]),
            { status: 200 },
          );
        }

        if (url.includes("/smart-comms/conversations/resolve")) {
          return new Response(JSON.stringify({
            id: "conv-1",
            user_id: "11111111-1111-1111-1111-111111111111",
            context_type: "dashboard",
            context_id: null,
            route_path: "/orders/new",
            title: null,
            created_at: "2026-05-17T10:00:00Z",
            updated_at: "2026-05-17T10:00:00Z",
          }), { status: 200 });
        }

        if (url.includes("/smart-comms/conversations/conv-1/messages")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }

        throw new Error(`Unexpected request: ${url}`);
      }),
    );

    renderOrderFormPage("create");

    expect(await screen.findByRole("heading", { name: /create order/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /cancel/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: /extract email into draft/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/source email text/i)).toBeInTheDocument();
    expect(screen.getByText(/fields marked with/i)).toBeInTheDocument();
    expect(screen.getAllByText((_, element) => element?.tagName === "SPAN" && element?.textContent === "Customer name*").length).toBeGreaterThan(0);
    expect(screen.getAllByText((_, element) => element?.tagName === "SPAN" && element?.textContent === "Origin*").length).toBeGreaterThan(0);
    expect(screen.getByText(/^commercial$/i)).toBeInTheDocument();
    expect(screen.getByText(/^route$/i)).toBeInTheDocument();
    expect(screen.getByText(/^cargo$/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Madrid, ES")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Paris, FR")).toBeInTheDocument();
  });

  it("create mode delegates pasted email extraction into intake review", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/truck-types")) {
        return new Response(JSON.stringify([{ id: 1, name: "mega" }]), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/resolve")) {
        return new Response(JSON.stringify({
          id: "conv-1",
          user_id: "11111111-1111-1111-1111-111111111111",
          context_type: "dashboard",
          context_id: null,
          route_path: "/orders/new",
          title: null,
          created_at: "2026-05-17T10:00:00Z",
          updated_at: "2026-05-17T10:00:00Z",
        }), { status: 200 });
      }

      if (url.includes("/smart-comms/conversations/conv-1/messages")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }

      if (url.endsWith("/orders/delegated-actions") && method === "POST") {
        return new Response(JSON.stringify({
          delegated_to: "ingestion",
          activity: {
            id: "activity-1",
            agent_kind: "orchestrator",
            activity_state: "completed",
            load_order_id: "order-2",
            title: "Delegated intake extraction completed",
            detail: "Orchestrator routed pasted email text to intake extraction.",
            activity_key: "delegated_intake_extraction",
            next_action: "Review extracted draft",
            metadata: { delegated_action: "extract_email_into_order_draft" },
            created_at: "2026-05-17T10:00:00Z",
          },
          ingestion_result: {
            ingestion_run_id: "run-1",
            route: "load_order_ingestion",
            run_status: "completed",
            load_order: {
              ...buildOrder({ id: "order-2" }),
            },
            extracted_payload: { customer_name: "Acme Logistics" },
            missing_fields: {},
            execution_path: "fallback",
            provider: null,
            model_name: null,
            trace_steps: [],
          },
          smart_comms_conversation: null,
          monitoring_snapshot: null,
        }), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url} ${method}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderOrderFormPage("create");

    expect(await screen.findByRole("heading", { name: /create order/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/source email text/i), { target: { value: "Customer: Acme Logistics" } });
    fireEvent.click(screen.getByRole("button", { name: /extract email into draft/i }));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/orders/order-2/intake");
    });
  });
});
