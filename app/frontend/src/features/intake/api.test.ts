import { afterEach, describe, expect, it, vi } from "vitest";

import {
  confirmViability,
  getHumanValidationContext,
  updateHumanValidation,
} from "./api";


describe("intake api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls the existing HITL endpoints with bearer auth", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ can_confirm_viability: true }), { status: 200 }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await getHumanValidationContext("order-1", async () => "session-token");
    await updateHumanValidation("order-1", async () => "session-token", {
      customer_name: "Acme",
    });
    await confirmViability("order-1", async () => "session-token", {
      review_notes: "Ready",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/orders/order-1/human-validation"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer session-token",
          "Content-Type": "application/json",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/orders/order-1/human-validation"),
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            customer_name: "Acme",
          }),
        }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("/orders/order-1/confirm-viability"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            review_notes: "Ready",
          }),
        }),
    );
  });
});
