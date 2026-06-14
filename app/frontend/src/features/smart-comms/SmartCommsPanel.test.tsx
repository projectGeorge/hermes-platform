import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { SmartCommsPanel } from "./SmartCommsPanel";

vi.mock("@clerk/react", () => ({
  useAuth: () => ({ getToken: async () => "mock-token" }),
  useUser: () => ({ user: null }),
  useSession: () => ({ session: null }),
}));

vi.mock("react-markdown", () => ({
  default: ({ children }: { children: string }) =>
    React.createElement("div", { "data-testid": "markdown" }, children),
}));


function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}


describe("SmartCommsPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  function renderPanel() {
    const queryClient = createQueryClient();
    const result = render(
      <QueryClientProvider client={queryClient}>
        <SmartCommsPanel
          contextType="dashboard"
          contextId={undefined}
          routePath="/dashboard"
          label="Dashboard"
        />
      </QueryClientProvider>,
    );
    return { ...result, queryClient };
  }

  it("does not fetch conversation data while collapsed", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderPanel();

    expect(await screen.findByRole("button", { name: /open smart comms/i })).toBeInTheDocument();
    await Promise.resolve();
    expect(fetchMock).not.toHaveBeenCalled();

    vi.unstubAllGlobals();
  });

  it("renders persisted history when the panel opens", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () =>
        new Response(
          JSON.stringify({
            id: "conv-1",
            user_id: "u1",
            context_type: "dashboard",
            context_id: null,
            route_path: "/dashboard",
            title: null,
            created_at: "2025-01-01T00:00:00Z",
            updated_at: "2025-01-01T00:00:00Z",
          }),
          { status: 200 },
        ),
      )
      .mockImplementationOnce(async () =>
        new Response(
          JSON.stringify([
            {
              id: "msg-1",
              conversation_id: "conv-1",
              role: "user",
              content: "Hello",
              metadata: null,
              created_at: "2025-01-01T00:00:00Z",
            },
            {
              id: "msg-2",
              conversation_id: "conv-1",
              role: "assistant",
              content: "Hi there!",
              metadata: null,
              created_at: "2025-01-01T00:00:01Z",
            },
          ]),
          { status: 200 },
        ),
      );

    vi.stubGlobal("fetch", fetchMock);

    renderPanel();

    const openButton = await screen.findByRole("button", { name: /open smart comms/i });
    await userEvent.click(openButton);

    expect(await screen.findByText("Hello")).toBeTruthy();
    expect(screen.getByTestId("markdown")).toBeTruthy();

    vi.unstubAllGlobals();
  });

  it("renders streaming draft separately from persisted history", async () => {
    const conversationResponse = {
      id: "conv-2",
      user_id: "u1",
      context_type: "dashboard",
      context_id: null,
      route_path: "/dashboard",
      title: null,
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z",
    };

    const historyPreStream = [
      {
        id: "msg-a",
        conversation_id: "conv-2",
        role: "user" as const,
        content: "What's up?",
        metadata: null,
        created_at: "2025-01-01T00:00:00Z",
      },
    ];

    const historyPostStream = [
      ...historyPreStream,
      {
        id: "msg-b",
        conversation_id: "conv-2",
        role: "assistant" as const,
        content: "Streaming reply",
        metadata: null,
        created_at: "2025-01-01T00:00:01Z",
      },
    ];

    let historyCallCount = 0;

    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, _opts?: RequestInit) => {
        const url = String(_url);
        if (url.includes("resolve")) {
          return new Response(JSON.stringify(conversationResponse), { status: 200 });
        }
        if (url.includes("messages/stream")) {
          const encoder = new TextEncoder();
          const stream = new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(
                encoder.encode(
                  'event: conversation\ndata: {"conversation_id":"conv-2"}\n\n',
                ),
              );
              controller.enqueue(
                encoder.encode(
                  'event: delta\ndata: {"chunk":"Streaming"}\n\n',
                ),
              );
              controller.enqueue(
                encoder.encode(
                  'event: done\ndata: {"conversation_id":"conv-2","message_id":"msg-b"}\n\n',
                ),
              );
              controller.close();
            },
          });
          return new Response(stream, { status: 200 });
        }
        if (url.includes("/messages")) {
          historyCallCount++;
          return new Response(
            JSON.stringify(historyCallCount === 1 ? historyPreStream : historyPostStream),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );

    renderPanel();

    const openButton = await screen.findByRole("button", { name: /open smart comms/i });
    await userEvent.click(openButton);

    expect(await screen.findByText("What's up?")).toBeTruthy();

    const textarea = screen.getAllByPlaceholderText(/ask about this page/i)[0];
    await userEvent.type(textarea, "Tell me more");
    await userEvent.click(screen.getByText("Send"));

    // Stream completes and invalidates history, causing refetch
    expect(await screen.findByText("Streaming reply")).toBeTruthy();

    vi.unstubAllGlobals();
  });

  it("refreshes persisted history when streaming fails after saving the user message", async () => {
    const conversationResponse = {
      id: "conv-3",
      user_id: "u1",
      context_type: "dashboard",
      context_id: null,
      route_path: "/dashboard",
      title: null,
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z",
    };

    const historyBeforeSend: Array<{
      id: string;
      conversation_id: string;
      role: "user" | "assistant";
      content: string;
      metadata: null;
      created_at: string;
    }> = [];

    const historyAfterFailure = [
      {
        id: "msg-user-1",
        conversation_id: "conv-3",
        role: "user" as const,
        content: "Need help",
        metadata: null,
        created_at: "2025-01-01T00:00:01Z",
      },
    ];

    let historyCallCount = 0;

    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, _opts?: RequestInit) => {
        const url = String(_url);
        if (url.includes("resolve")) {
          return new Response(JSON.stringify(conversationResponse), { status: 200 });
        }
        if (url.includes("messages/stream")) {
          const encoder = new TextEncoder();
          const stream = new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(
                encoder.encode(
                  'event: error\ndata: {"detail":"Model unavailable"}\n\n',
                ),
              );
              controller.close();
            },
          });
          return new Response(stream, { status: 200 });
        }
        if (url.includes("/messages")) {
          historyCallCount++;
          return new Response(
            JSON.stringify(historyCallCount === 1 ? historyBeforeSend : historyAfterFailure),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );

    renderPanel();

    const openButton = await screen.findByRole("button", { name: /open smart comms/i });
    await userEvent.click(openButton);

    const textarea = screen.getAllByPlaceholderText(/ask about this page/i)[0];
    await userEvent.type(textarea, "Need help");
    await userEvent.click(screen.getByText("Send"));

    expect(await screen.findByText("Need help")).toBeTruthy();

    vi.unstubAllGlobals();
  });
});
