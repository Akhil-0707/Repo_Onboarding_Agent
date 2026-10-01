import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockFetch, renderWithProviders } from "../test/utils";
import { ModelBanner } from "./ModelBanner";

const health = (online: boolean) => ({
  online,
  model: "Qwen/Qwen3-8B",
  latency_ms: online ? 120 : null,
  checked_at: "2026-10-01T00:00:00Z",
  error: online ? null : "unreachable",
});

describe("ModelBanner", () => {
  it("shows the offline banner when the model is down", async () => {
    mockFetch(() => jsonResponse(health(false)));
    renderWithProviders(<ModelBanner />);
    expect(await screen.findByText(/AI model is offline/i)).toBeInTheDocument();
  });

  it("renders nothing when the model is online", async () => {
    const spy = mockFetch(() => jsonResponse(health(true)));
    renderWithProviders(<ModelBanner />);
    await waitFor(() => expect(spy).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("warns when the backend itself is unreachable", async () => {
    mockFetch(() => {
      throw new TypeError("Failed to fetch");
    });
    renderWithProviders(<ModelBanner />);
    expect(await screen.findByText(/Cannot reach the RepoGuide server/i)).toBeInTheDocument();
  });
});
