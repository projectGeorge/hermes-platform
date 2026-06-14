import { describe, expect, it, vi } from "vitest";
import { SSEEvent, streamSSE } from "./apiClient";

function createSSEResponse(body: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

async function collectEvents(generator: AsyncGenerator<SSEEvent>): Promise<SSEEvent[]> {
  const events: SSEEvent[] = [];
  for await (const event of generator) {
    events.push(event);
  }
  return events;
}


describe("SSE stream parser (apiClient.streamSSE)", () => {
  it("parses delta, done, and error events from valid SSE blocks", async () => {
    const sseBody = [
      'event: conversation\ndata: {"conversation_id":"abc-123"}\n\n',
      'event: delta\ndata: {"chunk":"Hello"}\n\n',
      'event: delta\ndata: {"chunk":" world"}\n\n',
      'event: done\ndata: {"conversation_id":"abc-123","message_id":"msg-1"}\n\n',
    ].join("");

    vi.stubGlobal("fetch", vi.fn(async () => createSSEResponse(sseBody)));

    const events = await collectEvents(
      streamSSE("/test", async () => "token", {}),
    );

    expect(events).toHaveLength(4);
    expect(events[0].event).toBe("conversation");
    expect(JSON.parse(events[0].data)).toEqual({ conversation_id: "abc-123" });
    expect(events[1].event).toBe("delta");
    expect(JSON.parse(events[1].data)).toEqual({ chunk: "Hello" });
    expect(events[2].event).toBe("delta");
    expect(JSON.parse(events[2].data)).toEqual({ chunk: " world" });
    expect(events[3].event).toBe("done");
    expect(JSON.parse(events[3].data)).toEqual({
      conversation_id: "abc-123",
      message_id: "msg-1",
    });

    vi.unstubAllGlobals();
  });

  it("preserves embedded newlines in JSON delta payloads", async () => {
    const multilineContent = "## Summary\n- item 1\n- **item 2**\n\nDone.";
    const jsonPayload = JSON.stringify({ chunk: multilineContent });
    const sseBody = `event: delta\ndata: ${jsonPayload}\n\n`;

    vi.stubGlobal("fetch", vi.fn(async () => createSSEResponse(sseBody)));

    const events = await collectEvents(
      streamSSE("/test", async () => "token", {}),
    );

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("delta");
    const parsed = JSON.parse(events[0].data);
    expect(parsed.chunk).toBe(multilineContent);
    expect(parsed.chunk).toContain("\n");

    vi.unstubAllGlobals();
  });

  it("parses error events with detail", async () => {
    const sseBody = 'event: error\ndata: {"detail":"Model unavailable"}\n\n';

    vi.stubGlobal("fetch", vi.fn(async () => createSSEResponse(sseBody)));

    const events = await collectEvents(
      streamSSE("/test", async () => "token", {}),
    );

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("error");
    expect(JSON.parse(events[0].data)).toEqual({ detail: "Model unavailable" });

    vi.unstubAllGlobals();
  });

  it("combines multi-line data blocks correctly", async () => {
    const sseBody =
      "event: delta\n" +
      'data: {"chunk":"line1\\nline2"}\n' +
      "\n";

    vi.stubGlobal("fetch", vi.fn(async () => createSSEResponse(sseBody)));

    const events = await collectEvents(
      streamSSE("/test", async () => "token", {}),
    );

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("delta");
    const parsed = JSON.parse(events[0].data);
    expect(parsed.chunk).toContain("\n");

    vi.unstubAllGlobals();
  });

  it("handles chunked streaming across multiple reads", async () => {
    const parts = [
      'event: delta\ndata: {"chunk":"part 1"}\n\n',
      'event: delta\ndata: {"chunk":"part 2"}\n\n',
      'event: done\ndata: {"conversation_id":"cid","message_id":"mid"}\n\n',
    ];

    let partIndex = 0;
    const chunkedStream = new ReadableStream<Uint8Array>({
      async pull(controller) {
        if (partIndex < parts.length) {
          controller.enqueue(new TextEncoder().encode(parts[partIndex]));
          partIndex++;
        } else {
          controller.close();
        }
      },
    });

    const response = new Response(chunkedStream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });

    vi.stubGlobal("fetch", vi.fn(async () => response));

    const events = await collectEvents(
      streamSSE("/test", async () => "token", {}),
    );

    expect(events).toHaveLength(3);
    expect(JSON.parse(events[0].data).chunk).toBe("part 1");
    expect(JSON.parse(events[1].data).chunk).toBe("part 2");
    expect(events[2].event).toBe("done");

    vi.unstubAllGlobals();
  });
});
