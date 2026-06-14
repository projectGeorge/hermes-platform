import type { ReactNode } from "react";

import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { routes } from "./AppRouter";


const { useAuthMock } = vi.hoisted(() => ({
  useAuthMock: vi.fn(() => ({
    isLoaded: true,
    isSignedIn: false,
    getToken: vi.fn(),
  })),
}));


vi.mock("@clerk/react", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  SignIn: () => <div>Sign in</div>,
  SignUp: () => <div>Sign up</div>,
  UserButton: () => <button>User</button>,
  useAuth: useAuthMock,
}));


describe("AppRouter", () => {
  afterEach(() => {
    cleanup();
    useAuthMock.mockReset();
    useAuthMock.mockReturnValue({
      isLoaded: true,
      isSignedIn: false,
      getToken: vi.fn(),
    });
  });

  it("renders the landing page as a public product surface", () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/"] });

    render(<RouterProvider router={router} />);

    expect(screen.getAllByLabelText(/hermes logo/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /^sign in$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start for free/i })).toBeInTheDocument();
    expect(screen.getByText(/driven by specialized ai agents/i)).toBeInTheDocument();
    expect(screen.getByText(/smart intake/i)).toBeInTheDocument();
    expect(screen.getByText(/carrier match/i)).toBeInTheDocument();
  });

  it("shows a go to dashboard CTA when the user is signed in", () => {
    useAuthMock.mockReturnValue({
      isLoaded: true,
      isSignedIn: true,
      getToken: vi.fn(),
    });

    const router = createMemoryRouter(routes, { initialEntries: ["/"] });

    render(<RouterProvider router={router} />);

    expect(screen.getByRole("link", { name: /go to dashboard/i })).toBeInTheDocument();
  });

  it("renders the Hermes-branded sign in frame when redirecting signed-out users from /dashboard", async () => {
    useAuthMock.mockReturnValue({
      isLoaded: true,
      isSignedIn: false,
      getToken: vi.fn(),
    });

    const router = createMemoryRouter(routes, { initialEntries: ["/dashboard"] });

    render(<RouterProvider router={router} />);

    expect((await screen.findAllByLabelText(/hermes logo/i)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^sign in$/i).length).toBeGreaterThan(0);
  });
});
