import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { UserUsage } from "../api/usage";
import { formatCost } from "../api/usage";
import { jsonResponse, mockFetch, renderWithProviders } from "../test/utils";
import { UsageSummary } from "./UsageSummary";

function totals(total: number, calls = 3, latency = 12_500) {
  return {
    calls,
    prompt_tokens: total - 100,
    completion_tokens: 100,
    total_tokens: total,
    latency_ms: latency,
    est_cost: 0,
  };
}

function usage(overrides: Partial<UserUsage> = {}): UserUsage {
  return {
    totals: {
      analysis: totals(30_000, 9),
      chat: { ...totals(1_200, 2, 4_000), questions: 2 },
      all: totals(31_200, 11, 16_500),
    },
    repositories: [
      {
        id: "r1",
        full_name: "acme/api",
        commit_sha: "abcdef1234",
        on_dashboard: true,
        started_by_you: true,
        analysis: totals(30_000),
        chat: { ...totals(1_200), questions: 2 },
      },
      {
        id: "r2",
        full_name: "acme/web",
        commit_sha: "1234567890",
        on_dashboard: true,
        started_by_you: false,
        analysis: null,
        chat: null,
      },
    ],
    rate_limit: {
      new_analyses: {
        limit: 5,
        used: 5,
        remaining: 0,
        reset_in_seconds: 1500,
        window_seconds: 3600,
      },
      chat_questions: {
        limit: 30,
        used: 4,
        remaining: 26,
        reset_in_seconds: 0,
        window_seconds: 3600,
      },
    },
    pricing: { input_per_1k: 0, output_per_1k: 0, self_hosted: true },
    ...overrides,
  };
}

describe("UsageSummary", () => {
  it("shows tokens, model time, the self-hosted cost and the rate limit", async () => {
    mockFetch(() => jsonResponse(usage()));
    renderWithProviders(<UsageSummary />);

    const metric = (await screen.findByText("Analysis tokens")).parentElement as HTMLElement;
    expect(within(metric).getByText("30,000")).toBeInTheDocument();
    expect(screen.getByText("9 model calls")).toBeInTheDocument();
    expect(screen.getByText("2 questions")).toBeInTheDocument();
    expect(screen.getByText("17 s")).toBeInTheDocument();
    expect(screen.getByText("≈$0 (self-hosted)")).toBeInTheDocument();
    expect(screen.getByText(/0 of 5 left this hour \(next one in 25 min\)/)).toBeInTheDocument();
    expect(screen.getByText(/26 of 30 left this hour\.$/)).toBeInTheDocument();

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("acme/api@abcdef1");
    expect(within(rows[1] as HTMLElement).getByRole("link")).toHaveAttribute("href", "/repos/r1");
    expect(rows[2]).toHaveTextContent("cached (free)");
  });

  it("formats real prices", () => {
    const priced = { input_per_1k: 0.5, output_per_1k: 1, self_hosted: false };
    expect(formatCost(1.234, priced)).toBe("≈$1.23");
    expect(formatCost(0.0012, priced)).toBe("≈$0.0012");
  });
});
