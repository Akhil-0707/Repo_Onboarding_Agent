/**
 * Server-Sent Events over fetch (EventSource cannot send an Authorization header or POST).
 */
import {
  API_BASE,
  CLIENT_HEADER,
  authHeaders,
  getUnauthorizedHandler,
  toApiError,
} from "../api/client";

export interface SSEMessage {
  event: string;
  data: string;
}

/** Incremental parser: feed text chunks, get complete messages back. */
export class SSEParser {
  private buffer = "";

  feed(chunk: string): SSEMessage[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const messages: SSEMessage[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const raw = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith(":")) continue; // comment / keep-alive
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "event") event = value;
        else if (field === "data") data.push(value);
      }
      if (data.length) messages.push({ event, data: data.join("\n") });
      boundary = this.buffer.indexOf("\n\n");
    }
    return messages;
  }
}

export interface StreamOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
  onMessage: (message: SSEMessage) => void;
}

async function open(path: string, options: StreamOptions, token?: string | null) {
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    ...CLIENT_HEADER,
    ...(token === undefined ? authHeaders() : authHeaders(token)),
  };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  return fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
    credentials: "include",
  });
}

/** Resolves when the server closes the stream; rejects on HTTP errors. */
export async function streamSSE(path: string, options: StreamOptions): Promise<void> {
  let response = await open(path, options);
  const refresh = getUnauthorizedHandler();
  if (response.status === 401 && refresh) {
    const token = await refresh();
    if (token) response = await open(path, options, token);
  }
  if (!response.ok || !response.body) {
    throw await toApiError(response);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SSEParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    for (const message of parser.feed(value)) options.onMessage(message);
  }
}
