import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createOrder,
  getDashboardLoadOrderSummary,
  getOrder,
  listOrders,
  listOrdersPage,
  listTruckTypes,
  type LoadOrderMutationPayload,
  updateOrder,
} from "./api";

function buildOrder(overrides?: Record<string, unknown>) {
  return {
    id: "order-1",
    user_id: "22222222-2222-2222-2222-222222222222",
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

const baseMutationPayload: LoadOrderMutationPayload = {
  customer_name: "Acme Logistics",
  origin_text: "Madrid, ES",
  origin_load_date: "2026-05-04T09:30",
  destination_text: "Paris, FR",
  destination_unload_date: "2026-05-05T12:00",
  distance_km: "1270.00",
  cargo_description: "Ceramic tiles",
  weight_kg: "7800.00",
  truck_type_id: 1,
  adr_required: false,
  customer_price: "1400.00",
  currency: "EUR",
};


describe("listOrders", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests paginated orders batches and combines the typed payload", async () => {
    const getToken = vi.fn(async () => "session-token");
    const firstPage = Array.from({ length: 500 }, (_, index) => ({
      id: `order-${index}`,
      user_id: "22222222-2222-2222-2222-222222222222",
      customer_id: null,
      customer_name: `Customer ${index}`,
      status: "viability_pending",
      selected_trip_id: null,
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
      created_at: "2026-04-27T10:00:00",
      updated_at: "2026-04-27T10:05:00",
    }));
    const secondPage = [
      {
        id: "order-500",
        user_id: "22222222-2222-2222-2222-222222222222",
        customer_id: null,
        customer_name: "Acme Logistics",
        status: "viability_pending",
        selected_trip_id: null,
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
        created_at: "2026-04-27T10:00:00",
        updated_at: "2026-04-27T10:05:00",
      },
    ];
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(firstPage), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(secondPage), { status: 200 }));

    vi.stubGlobal("fetch", fetchMock);

    const orders = await listOrders(getToken);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/orders/?limit=500&skip=0"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer session-token",
          "Content-Type": "application/json",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/orders/?limit=500&skip=500"),
      expect.any(Object),
    );
    expect(orders).toHaveLength(501);
    expect(orders.at(-1)).toEqual(
      expect.objectContaining({
        id: "order-500",
        customer_name: "Acme Logistics",
        status: "viability_pending",
        truck_type_id: 1,
        created_at: "2026-04-27T10:00:00",
        updated_at: "2026-04-27T10:05:00",
      }),
    );
  });

  it("fetches one order with bearer auth", async () => {
    const getToken = vi.fn(async () => "session-token");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(buildOrder()), { status: 200 }));

    vi.stubGlobal("fetch", fetchMock);

    const order = await getOrder("order-1", getToken);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/orders/order-1"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer session-token",
          "Content-Type": "application/json",
        }),
      }),
    );
    expect(order).toEqual(expect.objectContaining({ id: "order-1", customer_name: "Acme Logistics" }));
  });

  it("fetches a paginated orders page with search and active filters", async () => {
    const getToken = vi.fn(async () => "session-token");
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          items: [buildOrder({ id: "order-page-1", customer_name: "Maria" })],
          total: 1,
          skip: 20,
          limit: 20,
        }),
        { status: 200 },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    const page = await listOrdersPage(getToken, {
      skip: 20,
      limit: 20,
      activeOnly: true,
      search: "maria",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/orders/page?skip=20&limit=20&active_only=true&search=maria"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer session-token" }),
      }),
    );
    expect(page.total).toBe(1);
    expect(page.items[0]?.customer_name).toBe("Maria");
  });

  it("fetches the dashboard load-order summary", async () => {
    const getToken = vi.fn(async () => "session-token");
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          active_order_count: 2,
          needs_attention_count: 1,
          attention_orders: [
            {
              id: "order-attention-1",
              customer_name: "Needs Review",
              status: "viability_pending",
              origin_text: "Madrid, ES",
              destination_text: "Paris, FR",
              updated_at: "2026-04-27T10:05:00",
            },
          ],
          recent_active_orders: [
            {
              id: "order-active-1",
              customer_name: "Ready Shipment",
              status: "formalized",
              origin_text: "Valencia, ES",
              destination_text: "Berlin, DE",
              updated_at: "2026-04-27T10:05:00",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    const summary = await getDashboardLoadOrderSummary(getToken);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/orders/summary?limit=5"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer session-token" }),
      }),
    );
    expect(summary.active_order_count).toBe(2);
    expect(summary.needs_attention_count).toBe(1);
    expect(summary.attention_orders[0]?.customer_name).toBe("Needs Review");
  });

  it("posts a create payload and returns the created order", async () => {
    const getToken = vi.fn(async () => "session-token");
    const createdOrder = buildOrder({ id: "order-created" });
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(createdOrder), { status: 201 }));

    vi.stubGlobal("fetch", fetchMock);

    const order = await createOrder(getToken, baseMutationPayload);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/orders/"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(baseMutationPayload),
      }),
    );
    expect(order).toEqual(expect.objectContaining({ id: "order-created" }));
  });

  it("sends a PUT request to update an order", async () => {
    const getToken = vi.fn(async () => "session-token");
    const updatedOrder = buildOrder({ customer_name: "Updated customer" });
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(updatedOrder), { status: 200 }));

    vi.stubGlobal("fetch", fetchMock);

    const order = await updateOrder("order-1", getToken, {
      ...baseMutationPayload,
      customer_name: "Updated customer",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/orders/order-1"),
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          ...baseMutationPayload,
          customer_name: "Updated customer",
        }),
      }),
    );
    expect(order).toEqual(expect.objectContaining({ customer_name: "Updated customer" }));
  });

  it("fetches truck types", async () => {
    const getToken = vi.fn(async () => "session-token");
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify([
          { id: 1, name: "mega" },
          { id: 2, name: "refrigerated" },
        ]),
        { status: 200 },
      )
    );

    vi.stubGlobal("fetch", fetchMock);

    const truckTypes = await listTruckTypes(getToken);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/truck-types"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer session-token" }),
      }),
    );
    expect(truckTypes).toEqual([
      { id: 1, name: "mega" },
      { id: 2, name: "refrigerated" },
    ]);
  });
});
