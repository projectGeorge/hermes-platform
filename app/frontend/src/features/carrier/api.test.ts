import { afterEach, describe, expect, it, vi } from "vitest";

import { getCarrierCandidates, runCarrierSearch, selectCarrier } from "./api";


describe("carrier api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses the persisted carrier-search endpoints", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ candidates: [] }), { status: 200 }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await runCarrierSearch("order-1", async () => "session-token");
    await getCarrierCandidates("order-1", async () => "session-token");
    await selectCarrier("order-1", async () => "session-token", { trip_id: "trip-1" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/orders/order-1/carrier-search"),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer session-token",
          "Content-Type": "application/json",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/orders/order-1/carrier-candidates"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer session-token",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("/orders/order-1/carrier-selection"),
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ trip_id: "trip-1" }),
      }),
    );
  });

  it("surfaces structured 404 details for missing carrier snapshots", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "Load order has no carrier-search snapshot" }), {
          status: 404,
        }),
      ),
    );

    await expect(
      getCarrierCandidates("order-1", async () => "session-token"),
    ).rejects.toMatchObject({
      status: 404,
      detail: "Load order has no carrier-search snapshot",
      message: "Load order has no carrier-search snapshot",
    });
  });
});
