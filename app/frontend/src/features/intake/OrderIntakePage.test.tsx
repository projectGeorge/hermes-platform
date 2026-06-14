import type { ReactNode } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrderIntakePage } from "./OrderIntakePage";
import type { HumanValidationContext } from "./api";


const navigateMock = vi.fn();


vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});


const getToken = vi.fn(async () => "session-token");


vi.mock("@clerk/react", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  SignIn: () => <div>Sign in</div>,
  SignUp: () => <div>Sign up</div>,
  UserButton: () => <button>User</button>,
  useAuth: () => ({ isLoaded: true, isSignedIn: true, getToken }),
}));


function renderOrderIntakePage(queryClient?: QueryClient) {
  const client = queryClient ?? new QueryClient({
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
      <MemoryRouter initialEntries={["/orders/order-1/intake"]}>
        <Routes>
          <Route path="/orders/:orderId/intake" element={<OrderIntakePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}


function buildContext(): HumanValidationContext {
  return {
    load_order: {
      id: "order-1",
      user_id: "11111111-1111-1111-1111-111111111111",
      customer_id: null,
      customer_name: "Acme Logistics",
      status: "viability_pending",
      selected_trip_id: null,
      origin_id: null,
      origin_text: "Madrid, ES",
      origin_load_date: null,
      destination_id: null,
      destination_text: null,
      destination_unload_date: null,
      distance_km: null,
      cargo_description: "Ceramic tiles",
      weight_kg: null,
      truck_type_id: null,
      adr_required: false,
      missing_fields: {
        destination_text: "not_found",
        origin_load_date: "not_found",
        destination_unload_date: "not_found",
        weight_kg: "not_found",
        customer_price: "not_found",
        distance_km: "not_found",
      },
      customer_price: null,
      currency: "EUR",
      created_at: "2026-04-30T10:00:00Z",
      updated_at: "2026-04-30T10:00:00Z",
    },
    latest_ingestion_run: {
      id: "run-1",
      route: "load_order_ingestion",
      status: "completed",
      raw_text: [
        "Customer: Acme Logistics",
        "Origin: Madrid, ES",
        "Cargo: Ceramic tiles",
      ].join("\n"),
      extracted_payload: {
        customer_name: "Acme Logistics",
        origin_text: "Madrid, ES",
        cargo_description: "Ceramic tiles",
      },
      execution_path: "model",
      provider: "lm_studio",
      model_name: "test-model",
      trace_steps: [
        { node: "model_extract", outcome: "success" },
        { node: "normalize", outcome: "done" },
        { node: "persist_load_order", outcome: "done" },
      ],
    },
    missing_fields: {
      destination_text: "not_found",
      origin_load_date: "not_found",
      destination_unload_date: "not_found",
      weight_kg: "not_found",
      customer_price: "not_found",
      distance_km: "not_found",
    },
    blocked_missing_fields: {},
    reviewable_fields: [
      "customer_name",
      "destination_text",
      "origin_text",
      "origin_load_date",
      "destination_unload_date",
      "distance_km",
      "cargo_description",
      "weight_kg",
      "truck_type_id",
      "customer_price",
      "currency",
      "adr_required",
    ],
    can_confirm_viability: false,
  };
}


describe("OrderIntakePage", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    navigateMock.mockReset();
  });

  it("renders review context, updates missing fields, and confirms viability", async () => {
    let currentContext = buildContext();
    let reviewPayload: Record<string, unknown> | null = null;
    let confirmPayload: Record<string, unknown> | null = null;

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

      if (url.includes("/orders/order-1/human-validation") && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify(currentContext), { status: 200 });
      }

      if (url.includes("/orders/order-1/human-validation") && init?.method === "PUT") {
        reviewPayload = JSON.parse(String(init.body));

        currentContext = {
          ...currentContext,
          load_order: {
            ...currentContext.load_order,
            destination_text: "Paris, FR",
            origin_load_date: "2026-05-04T09:30",
            destination_unload_date: "2026-05-05T12:00",
            distance_km: "1270.00",
            weight_kg: "7800.00",
            truck_type_id: 1,
            customer_price: "1250.50",
            currency: "EUR",
            adr_required: true,
            missing_fields: null,
          },
          missing_fields: {},
          can_confirm_viability: true,
        };

        return new Response(JSON.stringify(currentContext), { status: 200 });
      }

      if (url.includes("/orders/order-1/confirm-viability") && init?.method === "POST") {
        confirmPayload = JSON.parse(String(init.body));

        currentContext = {
          ...currentContext,
          load_order: {
            ...currentContext.load_order,
            status: "viability_confirmed",
          },
          can_confirm_viability: false,
        };

        return new Response(JSON.stringify(currentContext.load_order), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderOrderIntakePage();

    expect(await screen.findByRole("heading", { name: /intake & viability/i })).toBeInTheDocument();
    expect(screen.getAllByText(/missing/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/viability pending/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("listitem").some(el => /destination text/.test(el.textContent ?? ""))).toBe(true);
    expect(screen.getAllByRole("listitem").some(el => /origin load date/.test(el.textContent ?? ""))).toBe(true);
    expect(screen.getAllByRole("listitem").some(el => /destination unload date/.test(el.textContent ?? ""))).toBe(true);
    expect(screen.getAllByRole("listitem").some(el => /weight kg/.test(el.textContent ?? ""))).toBe(true);
    expect(screen.getAllByRole("listitem").some(el => /customer price/.test(el.textContent ?? ""))).toBe(true);
    expect(screen.getAllByRole("listitem").some(el => /distance km/.test(el.textContent ?? ""))).toBe(true);
    expect(screen.getAllByText(/load_order_ingestion/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/source request/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/customer: Acme Logistics/i)).toBeInTheDocument();
    expect(screen.getAllByText(/agent summary/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/customer name/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Acme Logistics/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText(/distance \(km\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/truck type/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^path$/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/^model$/)).toBeInTheDocument();
    expect(screen.getByText(/^lm_studio$/i)).toBeInTheDocument();
    expect(screen.getByText(/^test-model$/i)).toBeInTheDocument();
    expect(screen.getByText(/model_extract/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^success$/i).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText(/^destination$/i), { target: { value: "Paris, FR" } });
    fireEvent.change(screen.getByLabelText(/origin load date/i), { target: { value: "2026-05-04T09:30" } });
    fireEvent.change(screen.getByLabelText(/destination unload date/i), {
      target: { value: "2026-05-05T12:00" },
    });
    fireEvent.change(screen.getByLabelText(/distance \(km\)/i), { target: { value: "1270.00" } });
    fireEvent.change(screen.getByLabelText(/weight \(kg\)/i), { target: { value: "7800.00" } });
    fireEvent.change(screen.getByLabelText(/truck type/i), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/customer price/i), { target: { value: "1250.50" } });
    fireEvent.change(screen.getByLabelText(/currency/i), { target: { value: "EUR" } });
    fireEvent.click(screen.getByLabelText(/adr required/i));
    fireEvent.click(screen.getByRole("button", { name: /save review/i }));

    expect(await screen.findByText(/all fields present/i)).toBeInTheDocument();
    expect(screen.getByText(/viability pending/i)).toBeInTheDocument();

    const confirmButton = await screen.findByRole("button", { name: /confirm viability & search/i });
    await waitFor(() => {
      expect(confirmButton).not.toBeDisabled();
    });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url, init]) =>
        String(url).includes("/orders/order-1/confirm-viability")
        && (init as RequestInit | undefined)?.method === "POST")).toBe(true);
    });

    expect(reviewPayload).toMatchObject({
      destination_text: "Paris, FR",
      origin_load_date: "2026-05-04T09:30",
      destination_unload_date: "2026-05-05T12:00",
      distance_km: "1270.00",
      weight_kg: "7800.00",
      truck_type_id: 1,
      customer_price: "1250.50",
      currency: "EUR",
      adr_required: true,
    });
    expect(confirmPayload).toEqual({});
    expect(navigateMock).toHaveBeenCalledWith("/orders/order-1/carrier-match");
  });

  it("does not navigate away when saving review changes", async () => {
    let currentContext = buildContext();

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

      if (url.includes("/orders/order-1/human-validation") && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify(currentContext), { status: 200 });
      }

      if (url.includes("/orders/order-1/human-validation") && init?.method === "PUT") {
        currentContext = {
          ...currentContext,
          load_order: {
            ...currentContext.load_order,
            destination_text: "Paris, FR",
          },
          missing_fields: {
            origin_load_date: "not_found",
            destination_unload_date: "not_found",
            weight_kg: "not_found",
            customer_price: "not_found",
            distance_km: "not_found",
          },
        };
        return new Response(JSON.stringify(currentContext), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderOrderIntakePage();

    fireEvent.change(await screen.findByLabelText(/^destination$/i), { target: { value: "Paris, FR" } });
    fireEvent.click(screen.getByRole("button", { name: /save review/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/orders/order-1/human-validation"),
        expect.objectContaining({ method: "PUT" }),
      );
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("disables save review and shows a locked message when review is no longer editable", async () => {
    const currentContext = {
      ...buildContext(),
      load_order: {
        ...buildContext().load_order,
        status: "ready_for_formalization",
        destination_text: "Paris, FR",
        origin_load_date: "2026-05-04T09:30:00Z",
        destination_unload_date: "2026-05-05T12:00:00Z",
        distance_km: "1270.00",
        weight_kg: "7800.00",
        truck_type_id: 1,
        customer_price: "1250.50",
        missing_fields: null,
      },
      missing_fields: {},
      can_confirm_viability: false,
    } satisfies HumanValidationContext;

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

      if (url.includes("/orders/order-1/human-validation") && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify(currentContext), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderOrderIntakePage();

    const saveButton = await screen.findByRole("button", { name: /save review/i });

    expect(saveButton).toBeDisabled();
    expect(screen.getByText(/review is locked for this order status/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to order/i })).toBeInTheDocument();
  });

  it("only submits reviewable fields and saves dirty edits before confirming viability", async () => {
    let currentContext = {
      ...buildContext(),
      reviewable_fields: [
        "customer_name",
        "destination_text",
        "origin_text",
        "origin_load_date",
        "distance_km",
        "cargo_description",
        "weight_kg",
        "customer_price",
        "currency",
        "adr_required",
      ],
      can_confirm_viability: true,
      missing_fields: {},
      load_order: {
        ...buildContext().load_order,
        destination_text: "Paris, FR",
        origin_load_date: "2026-05-04T09:30",
        distance_km: "1270.00",
        weight_kg: "7800.00",
        customer_price: "1250.50",
        missing_fields: null,
      },
    } satisfies HumanValidationContext;
    let reviewPayload: Record<string, unknown> | null = null;

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

      if (url.includes("/orders/order-1/human-validation") && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify(currentContext), { status: 200 });
      }

      if (url.includes("/orders/order-1/human-validation") && init?.method === "PUT") {
        reviewPayload = JSON.parse(String(init.body));

        currentContext = {
          ...currentContext,
          load_order: {
            ...currentContext.load_order,
            customer_name: "Updated customer",
          },
        };

        return new Response(JSON.stringify(currentContext), { status: 200 });
      }

      if (url.includes("/orders/order-1/confirm-viability") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            ...currentContext.load_order,
            status: "viability_confirmed",
          }),
          { status: 200 },
        );
      }

      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderOrderIntakePage();

    const customerInput = await screen.findByLabelText(/customer name/i);

    fireEvent.change(customerInput, { target: { value: "Updated customer" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm viability & search/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/orders/order-1/human-validation"),
        expect.objectContaining({ method: "PUT" }),
      );
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/orders/order-1/confirm-viability"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(reviewPayload).toMatchObject({
      customer_name: "Updated customer",
    });
    expect(reviewPayload).not.toHaveProperty("destination_unload_date");
  });

  it("shows an error when the intake context request fails", async () => {
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

      if (url.includes("/orders/order-1/human-validation")) {
        return new Response("boom", { status: 500 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderOrderIntakePage();

    expect(await screen.findByText(/failed to load intake review/i)).toBeInTheDocument();
  });

  it("keeps unsaved edits during a background refetch", async () => {
    const currentContext = buildContext();
    let contextReads = 0;
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
        mutations: {
          retry: false,
        },
      },
    });

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

      if (url.includes("/orders/order-1/human-validation")) {
        contextReads += 1;
        return new Response(JSON.stringify(currentContext), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderOrderIntakePage(queryClient);

    const destinationInput = await screen.findByLabelText(/^destination$/i);

    fireEvent.change(destinationInput, { target: { value: "Paris, FR" } });
    expect(screen.getByLabelText(/^destination$/i)).toHaveValue("Paris, FR");

    await queryClient.invalidateQueries({ queryKey: ["orders", "order-1", "human-validation"] });
    await waitFor(() => {
      expect(contextReads).toBeGreaterThanOrEqual(2);
    });

    expect(screen.getByLabelText(/^destination$/i)).toHaveValue("Paris, FR");
  });
});
