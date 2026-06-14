import { env } from "./env";


export class ApiError extends Error {
  status: number;
  detail: string | null;

  constructor(status: number, detail: string | null, message?: string) {
    super(message ?? detail ?? "Request failed");
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}


export async function apiClient<T>(
  path: string,
  getToken: () => Promise<string | null>,
  init?: RequestInit,
): Promise<T> {
  const token = await getToken();
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const responseText = await response.text();

    try {
      const payload = JSON.parse(responseText) as { detail?: unknown };
      const detail = typeof payload.detail === "string" ? payload.detail : null;
      throw new ApiError(response.status, detail, detail ?? (responseText || "Request failed"));
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }

      throw new ApiError(response.status, null, responseText || "Request failed");
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}


export type SSEEvent = {
  event: string;
  data: string;
};


export async function* streamSSE(
  path: string,
  getToken: () => Promise<string | null>,
  body: Record<string, unknown>,
): AsyncGenerator<SSEEvent> {
  const token = await getToken();
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const responseText = await response.text();
    throw new ApiError(response.status, null, responseText || "Streaming request failed");
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      let currentEvent = "message";
      const dataParts: string[] = [];

      for (const line of lines) {
        if (line === "") {
          if (dataParts.length > 0) {
            yield { event: currentEvent, data: dataParts.join("\n") };
          }
          currentEvent = "message";
          dataParts.length = 0;
          continue;
        }

        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          dataParts.push(line.slice(6));
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
