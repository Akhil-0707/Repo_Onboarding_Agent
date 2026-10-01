import { describe, expect, it, vi } from "vitest";

import { mockFetch, sseResponse } from "../test/utils";
import { SSEParser, streamSSE } from "./sse";

describe("SSEParser", () => {
  it("handles messages split across chunks", () => {
    const parser = new SSEParser();
    expect(parser.feed('event: step\ndata: {"a":')).toEqual([]);
    expect(parser.feed("1}\n\nevent: log\ndata: x\n\n")).toEqual([
      { event: "step", data: '{"a":1}' },
      { event: "log", data: "x" },
    ]);
  });

  it("joins multi-line data, ignores comments and defaults the event name", () => {
    const parser = new SSEParser();
    expect(parser.feed(": keep-alive\n\ndata: line1\ndata: line2\n\n")).toEqual([
      { event: "message", data: "line1\nline2" },
    ]);
  });

  it("normalises CRLF line endings", () => {
    expect(new SSEParser().feed("event: end\r\ndata: {}\r\n\r\n")).toEqual([
      { event: "end", data: "{}" },
    ]);
  });
});

describe("streamSSE", () => {
  it("delivers parsed messages until the server closes the stream", async () => {
    mockFetch(() => sseResponse(["event: a\ndata: 1\n\n", "event: b\ndata: 2\n\n"]));
    const onMessage = vi.fn();
    await streamSSE("/api/x", { onMessage });
    expect(onMessage.mock.calls.map(([m]) => m.event)).toEqual(["a", "b"]);
  });

  it("rejects with the API error on HTTP failures", async () => {
    mockFetch(
      () =>
        new Response(JSON.stringify({ error: { code: "not_found", message: "Nope" } }), {
          status: 404,
        }),
    );
    await expect(streamSSE("/api/x", { onMessage: vi.fn() })).rejects.toMatchObject({
      status: 404,
      code: "not_found",
    });
  });
});
