import type { ReactNode } from "react";

import { cleanup, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { routes } from "../AppRouter";
import { AppProviders } from "../providers/AppProviders";


const getToken = vi.fn(async () => "session-token");


vi.mock("@clerk/react", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  SignIn: () => <div>Sign in</div>,
  SignUp: () => <div>Sign up</div>,
  UserButton: () => <button aria-label="User menu">User menu</button>,
  useAuth: () => ({ isLoaded: true, isSignedIn: true, getToken }),
}));

function getPrimaryNavLink(name: RegExp) {
  const nav = screen.getByRole("navigation");

  return nav.querySelector(`a[href='${name.source === "dashboard" ? "/dashboard" : "/orders"}']`);
}


describe("AppShell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            id: "11111111-1111-1111-1111-111111111111",
            email: "operator@example.com",
            operator_name: "Operator Demo",
            auth_id: "user_live_123",
          }),
          { status: 200 },
        ),
      ),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the branded shell frame with a stable primary navigation", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/dashboard"] });

    render(
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>,
    );

    const primaryNav = screen.getByRole("navigation", { name: /primary navigation/i });

    expect((await screen.findAllByText("Operator Demo")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByLabelText(/hermes logo/i).length).toBeGreaterThanOrEqual(1);
    expect(within(primaryNav).getByRole("link", { name: /^dashboard$/i })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: /^orders$/i })).toBeInTheDocument();
    expect(within(primaryNav).queryByRole("link", { name: /create order/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /user menu/i }).length).toBeGreaterThanOrEqual(1);
  });

  it("highlights dashboard as the active section on /dashboard", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/dashboard"] });

    render(
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>,
    );

    await screen.findAllByText("Operator Demo");

    const dashboardLink = getPrimaryNavLink(/dashboard/i);
    const ordersLink = getPrimaryNavLink(/orders/i);

    expect(dashboardLink).toHaveAttribute("aria-current", "page");
    expect(ordersLink).not.toHaveAttribute("aria-current", "page");
  });

  it("highlights orders as the active section on /orders", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/orders"] });

    render(
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>,
    );

    await screen.findAllByText("Operator Demo");

    const ordersLink = getPrimaryNavLink(/orders/i);
    const dashboardLink = getPrimaryNavLink(/dashboard/i);

    expect(ordersLink).toHaveAttribute("aria-current", "page");
    expect(dashboardLink).not.toHaveAttribute("aria-current", "page");
  });
});
