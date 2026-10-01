import { describe, expect, it } from "vitest";

import { jsonResponse, mockFetch } from "../test/utils";
import { ApiError, apiFetch, setAccessTokenProvider } from "./client";

describe("apiFetch", () => {
  it("returns parsed JSON on success and sends the bearer token", async () => {
    setAccessTokenProvider(() => "tok");
    const spy = mockFetch(() => jsonResponse({ ok: true }));

    await expect(apiFetch("/api/x")).resolves.toEqual({ ok: true });
    const headers = new Headers(spy.mock.calls[0]?.[1]?.headers);
    expect(headers.get("Authorization")).toBe("Bearer tok");
    setAccessTokenProvider(() => null);
  });

  it("maps the error envelope to ApiError", async () => {
    mockFetch(() =>
      jsonResponse(
        {
          error: {
            code: "rate_limited",
            message: "Slow down",
            details: { retry_after_seconds: 5 },
          },
        },
        429,
      ),
    );

    const error = await apiFetch("/api/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 429, code: "rate_limited", message: "Slow down" });
  });

  it("handles non-JSON error bodies", async () => {
    mockFetch(() => new Response("<html>Bad gateway</html>", { status: 502 }));
    await expect(apiFetch("/api/x")).rejects.toMatchObject({ status: 502, code: "http_error" });
  });

  it("reports network failures", async () => {
    mockFetch(() => {
      throw new TypeError("Failed to fetch");
    });
    await expect(apiFetch("/api/x")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });
});
